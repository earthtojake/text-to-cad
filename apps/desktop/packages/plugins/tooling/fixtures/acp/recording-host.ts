/**
 * Minimal standalone AcpProcessHost for fixture recording scripts.
 *
 * Deliberately avoids importing any `@main/*` / Electron-specific modules so
 * the scripts run in plain Node (--experimental-strip-types) without the full
 * Electron main-process boot.
 *
 * CLI resolution priority for a given provider:
 *   1. `EMDASH_<PROVIDERID_UPPER>_BIN` env var (e.g. EMDASH_CLAUDE_BIN)
 *   2. `EMDASH_CLI_PATH` env var (generic override)
 *   3. `which <binaryName>` via node:child_process
 */
import { spawn, execSync } from 'node:child_process';
import { EventEmitter } from 'node:events';
import { realpathSync } from 'node:fs';
import { mkdir, readFile, writeFile } from 'node:fs/promises';
import type {
  AcpFs,
  AcpProcessHandle,
  AcpProcessHost,
  AcpTerminalExit,
  AcpTerminalProcess,
} from '@emdash/core/runtimes/acp/api/transport';

class RecordingProcessHandle implements AcpProcessHandle {
  constructor(private readonly child: ReturnType<typeof spawn>) {}

  get stdin() {
    if (!this.child.stdin) throw new Error('RecordingProcessHandle: no stdin');
    return this.child.stdin;
  }

  get stdout() {
    if (!this.child.stdout) throw new Error('RecordingProcessHandle: no stdout');
    return this.child.stdout;
  }

  get stderr() {
    return this.child.stderr ?? undefined;
  }

  get exitCode() {
    return this.child.exitCode;
  }

  onExit(cb: (code: number | null) => void): void {
    this.child.on('exit', (code) => cb(code));
  }

  onError(cb: (err: Error) => void): void {
    this.child.on('error', cb);
  }

  kill(signal?: NodeJS.Signals): void {
    this.child.kill(signal ?? 'SIGTERM');
  }
}

class RecordingTerminalProcess extends EventEmitter implements AcpTerminalProcess {
  private _exitCode: number | null = null;

  constructor(private readonly child: ReturnType<typeof spawn>) {
    super();
    child.on('exit', (code, signal) => {
      this._exitCode = code;
      this.emit('exit', { exitCode: code, signal: signal ?? null } satisfies AcpTerminalExit);
    });
    child.on('error', (err) => this.emit('error', err));
  }

  get stdout() {
    if (!this.child.stdout) throw new Error('RecordingTerminalProcess: no stdout');
    return this.child.stdout;
  }

  get stderr() {
    return this.child.stderr ?? undefined;
  }

  get exitCode() {
    return this._exitCode;
  }

  onExit(cb: (status: AcpTerminalExit) => void): void {
    this.on('exit', cb);
  }

  onError(cb: (err: Error) => void): void {
    this.on('error', cb);
  }

  kill(signal?: NodeJS.Signals): void {
    this.child.kill(signal ?? 'SIGTERM');
  }
}

const recordingFs: AcpFs = {
  readFile: (path, encoding) => readFile(path, encoding),
  writeFile: (path, content, encoding) => writeFile(path, content, encoding),
  mkdir: (path, opts) => mkdir(path, opts),
};

/** Map of provider id → common binary names (first entry is tried first). */
const PROVIDER_BINARY_NAMES: Record<string, string[]> = {
  claude: ['claude'],
  codex: ['codex'],
  opencode: ['opencode'],
};

function resolveBinary(providerId: string): string {
  const envKey = `EMDASH_${providerId.toUpperCase()}_BIN`;
  const fromEnv = process.env[envKey] ?? process.env['EMDASH_CLI_PATH'];
  if (fromEnv) return fromEnv;

  // Strip workspace node_modules/.bin directories from PATH before calling
  // `which`. When running via pnpm scripts, pnpm injects these at the front
  // of PATH; a workspace shim (e.g. node_modules/.bin/codex) would otherwise
  // shadow the globally-installed binary, resolving to a broken workspace copy
  // that may be missing platform-native optional dependencies.
  const cleanPath = (process.env['PATH'] ?? '')
    .split(':')
    .filter((p) => !p.includes('node_modules/.bin'))
    .join(':');

  const names = PROVIDER_BINARY_NAMES[providerId] ?? [providerId];
  for (const name of names) {
    try {
      const found = execSync(`which ${name}`, {
        encoding: 'utf8',
        env: { ...process.env, PATH: cleanPath },
      }).trim();
      // Resolve symlinks so agent adapters that use `import.meta.url`-based
      // require resolution find the correct native dependencies.
      if (found) return realpathSync(found);
    } catch {
      // not found in PATH, try next
    }
  }

  throw new Error(
    `RecordingHost: cannot resolve binary for provider '${providerId}'. ` +
      `Set ${envKey} or EMDASH_CLI_PATH, or ensure the CLI is in PATH.`
  );
}

/**
 * Standalone AcpProcessHost for fixture scripts.
 *
 * Passes through a minimal, safe env subset to the spawned agent adapter:
 * HOME, PATH, TMPDIR, ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY,
 * TERM, LANG, and any `EMDASH_*` / `CLAUDE_CODE_*` vars the caller sets.
 */
export class RecordingHost implements AcpProcessHost {
  readonly fs: AcpFs = recordingFs;

  async resolveSpawnContext(
    providerId: string
  ): Promise<{ cli: string; agentEnv: Record<string, string> }> {
    const cli = resolveBinary(providerId);

    const safeKeys = [
      'HOME',
      'PATH',
      'TMPDIR',
      'TEMP',
      'TMP',
      'TERM',
      'LANG',
      'LC_ALL',
      'USER',
      'LOGNAME',
      'SHELL',
      // API keys
      'ANTHROPIC_API_KEY',
      'OPENAI_API_KEY',
      'GEMINI_API_KEY',
      'GOOGLE_API_KEY',
      'CODEX_API_KEY',
      // Agent-specific
      'CLAUDE_CODE_EXECUTABLE',
      'ELECTRON_RUN_AS_NODE',
    ];
    // Also pass any env vars prefixed with EMDASH_ or the provider's uppercase name
    const prefixes = ['EMDASH_', providerId.toUpperCase() + '_'];

    const agentEnv: Record<string, string> = {};
    for (const [k, v] of Object.entries(process.env)) {
      if (!v) continue;
      if (safeKeys.includes(k) || prefixes.some((p) => k.startsWith(p))) {
        agentEnv[k] = v;
      }
    }

    return { cli, agentEnv };
  }

  async spawn(spec: {
    command: string;
    args: string[];
    env: Record<string, string>;
    cwd: string;
  }): Promise<AcpProcessHandle> {
    const child = spawn(spec.command, spec.args, {
      cwd: spec.cwd,
      env: spec.env,
      stdio: ['pipe', 'pipe', 'pipe'],
    });

    if (!child.stdin || !child.stdout) {
      throw new Error('RecordingHost: failed to spawn agent — no stdio');
    }

    return new RecordingProcessHandle(child);
  }

  async spawnTerminal(spec: {
    command: string;
    args: string[];
    env: Record<string, string>;
    cwd: string;
  }): Promise<AcpTerminalProcess> {
    const child = spawn(spec.command, spec.args, {
      cwd: spec.cwd,
      env: spec.env,
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    if (!child.stdout) {
      throw new Error('RecordingHost: failed to spawn terminal — no stdout');
    }

    return new RecordingTerminalProcess(child);
  }
}
