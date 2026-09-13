/**
 * Generic ACP transcript fixture generator.
 *
 * Prerequisites (must be satisfied before running):
 *   1. Workspace packages built: run `pnpm build` from the repo root so that
 *      @emdash/core/runtimes/acp/api, @emdash/core/runtimes/acp/node, and @emdash/plugins resolve from dist.
 *   2. Target agent CLI installed and authenticated, e.g. `claude` on PATH.
 *   3. Network + API-token access (real model calls are made).
 *
 * Usage (from packages/plugins):
 *   pnpm fixtures:acp [--provider claude] [--model claude-sonnet-5] \
 *     [--cwd /tmp/my-worktree] [--out src/agents/impl/claude/fixtures/acp-transcript.json]
 *
 * Environment overrides:
 *   EMDASH_<PROVIDERID_UPPER>_BIN   - absolute path to the provider CLI binary
 *   EMDASH_CLI_PATH                 - generic CLI binary path override
 *
 * Safety: by default a throw-away `git worktree` is created from HEAD so all
 * agent file edits are isolated. Pass --cwd to run in-place or against an
 * external clone. The worktree is removed in a finally block.
 */
import { execSync, execFileSync } from 'node:child_process';
import { resolve, isAbsolute } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createAcpAgentConnection } from '@emdash/core/runtimes/acp/node';
import { createScope } from '@emdash/shared/concurrency';
import { pluginRegistry } from '../../src/agents/registry';
import { Recorder } from './acp/recorder';
import { buildRecordingClient } from './acp/recording-client';
import { RecordingHost } from './acp/recording-host';
import { scenario, type ConfigOption, type SessionMode } from './acp/scenario';

export interface TranscriptOptions {
  /** Registered provider id, e.g. 'claude'. */
  providerId: string;
  /** Optional model override — passed to newSession if not null. */
  model?: string | null;
  /**
   * Working directory for the agent session.
   * When omitted a throwaway git worktree is created at HEAD and removed on exit.
   */
  cwd?: string;
  /**
   * Output file path. Defaults to
   * `src/agents/impl/<providerId>/fixtures/acp-transcript.json`
   * relative to the package root (packages/plugins).
   */
  out?: string;
}

function repoRoot(): string {
  return execSync('git rev-parse --show-toplevel', { encoding: 'utf8' }).trim();
}

function createWorktree(): string {
  const root = repoRoot();
  const branch = execSync('git rev-parse --abbrev-ref HEAD', { encoding: 'utf8' }).trim();
  const tmpDir = `/tmp/emdash-acp-fixture-${Date.now()}`;
  console.log(`[fixture] Creating throwaway worktree at ${tmpDir} (branch: ${branch})`);
  execFileSync('git', ['worktree', 'add', '--detach', tmpDir, 'HEAD'], {
    cwd: root,
    stdio: 'inherit',
  });
  return tmpDir;
}

function removeWorktree(path: string): void {
  try {
    const root = repoRoot();
    execFileSync('git', ['worktree', 'remove', '--force', path], {
      cwd: root,
      stdio: 'inherit',
    });
    console.log(`[fixture] Removed worktree ${path}`);
  } catch (e) {
    console.warn(`[fixture] Could not remove worktree ${path}:`, e);
  }
}

export async function runAcpTranscript(opts: TranscriptOptions): Promise<void> {
  const plugin = pluginRegistry.get(opts.providerId);
  if (!plugin) {
    throw new Error(`[fixture] Unknown provider '${opts.providerId}'. Is it registered?`);
  }
  if (plugin.capabilities.acp.kind !== 'supported' || !plugin.behavior?.acp) {
    throw new Error(`[fixture] Provider '${opts.providerId}' does not support ACP transport.`);
  }
  const behavior = plugin.behavior.acp;

  const outPath = opts.out
    ? isAbsolute(opts.out)
      ? opts.out
      : resolve(process.cwd(), opts.out)
    : resolve(process.cwd(), `src/agents/impl/${opts.providerId}/fixtures/acp-transcript.json`);

  let worktreePath: string | null = null;
  let cwd: string;
  if (opts.cwd) {
    cwd = isAbsolute(opts.cwd) ? opts.cwd : resolve(process.cwd(), opts.cwd);
    console.log(`[fixture] Using caller-supplied cwd: ${cwd}`);
  } else {
    cwd = createWorktree();
    worktreePath = cwd;
  }

  const recorder = new Recorder({
    providerId: opts.providerId,
    model: opts.model ?? null,
    cwd,
  });
  const host = new RecordingHost();

  let sessionId: string | null = null;
  const { client, dispose: disposeClient } = buildRecordingClient(recorder, host, () => sessionId);
  const scope = createScope({ label: `acp-fixture:${opts.providerId}` });
  const spawnContext = await host.resolveSpawnContext(opts.providerId);
  const spawn = behavior.buildSpawn({
    cwd,
    env: spawnContext.agentEnv,
    cli: spawnContext.cli,
  });

  const connResult = await createAcpAgentConnection(
    { host, behavior },
    {
      providerId: opts.providerId,
      spawn: {
        ...spawn,
        env: { ...spawnContext.agentEnv, ...spawn.env },
        cwd,
      },
      scope,
      buildClient: () => client,
      onClosed: (exitCode) => {
        console.log(`[fixture] Agent process closed (code ${exitCode ?? 'null'}).`);
      },
    }
  );

  if (!connResult.success) {
    await scope.dispose();
    if (worktreePath) removeWorktree(worktreePath);
    throw new Error(`[fixture] Connection failed: ${JSON.stringify(connResult.error)}`);
  }

  const { agent, supportsLoadSession } = connResult.data;

  try {
    console.log('[fixture] Initialized.', { supportsLoadSession });

    console.log('[fixture] Calling newSession…');
    const sessionResp = await agent.newSession({ cwd, mcpServers: [] });
    sessionId = sessionResp.sessionId;
    console.log(`[fixture] Session started: ${sessionId}`);

    const initialModes = sessionResp.modes?.availableModes ?? [];
    const initialConfigOptions = sessionResp.configOptions ?? [];

    recorder.meta = {
      ...recorder.meta,
      sessionId,
      generatedAt: new Date().toISOString(),
      initialModes,
      initialConfigOptions,
      initialAvailableCommands: null,
    };

    let stepIndex = 0;
    for (const step of scenario) {
      stepIndex++;
      console.log(`\n[fixture] Step ${stepIndex}/${scenario.length}: kind=${step.kind}`);

      if (!sessionId) {
        console.warn('[fixture] No active sessionId — skipping step');
        continue;
      }

      if (step.kind === 'prompt') {
        const content = [{ type: 'text' as const, text: step.text }];
        recorder.record({ kind: 'prompt', sessionId, content });

        console.log(`[fixture] → prompt: "${step.text.slice(0, 60)}…"`);
        const promptResp = await agent.prompt({ sessionId, prompt: content });
        const stopReason = promptResp.stopReason ?? null;
        console.log(`[fixture] ← stopReason: ${stopReason}`);
        recorder.record({ kind: 'prompt_result', sessionId, stopReason });
      } else if (step.kind === 'setModel') {
        if (!agent.setSessionConfigOption) {
          console.log(
            '[fixture] Agent does not support setSessionConfigOption — skipping setModel'
          );
          continue;
        }
        const modelValue = step.resolveModel(initialConfigOptions as ConfigOption[]);
        if (!modelValue) {
          console.log('[fixture] No alternative model found — skipping setModel');
          continue;
        }
        console.log(`[fixture] → setSessionConfigOption model=${modelValue}`);
        const resp = await agent.setSessionConfigOption({
          sessionId,
          configId: 'model',
          value: modelValue,
        });
        recorder.record({
          kind: 'config_option_set',
          sessionId,
          configId: 'model',
          value: modelValue,
          responseConfigOptions: resp?.configOptions ?? null,
        });
      } else if (step.kind === 'setEffort') {
        if (!agent.setSessionConfigOption) {
          console.log(
            '[fixture] Agent does not support setSessionConfigOption — skipping setEffort'
          );
          continue;
        }
        const effortConfig = initialConfigOptions.find(
          (c) =>
            c.category === 'thought_level' ||
            c.id === 'thought_level' ||
            c.id === 'effort' ||
            c.id.toLowerCase().includes('effort') ||
            c.id.toLowerCase().includes('thinking')
        );
        if (!effortConfig) {
          console.log('[fixture] No effort config found — skipping setEffort');
          continue;
        }
        const effortValue = step.resolveEffort(initialConfigOptions as ConfigOption[]);
        if (!effortValue) {
          console.log('[fixture] No alternative effort value found — skipping setEffort');
          continue;
        }
        console.log(`[fixture] → setSessionConfigOption ${effortConfig.id}=${effortValue}`);
        const resp = await agent.setSessionConfigOption({
          sessionId,
          configId: effortConfig.id,
          value: effortValue,
        });
        recorder.record({
          kind: 'config_option_set',
          sessionId,
          configId: effortConfig.id,
          value: effortValue,
          responseConfigOptions: resp?.configOptions ?? null,
        });
      } else if (step.kind === 'setMode') {
        if (!agent.setSessionMode) {
          console.log('[fixture] Agent does not support setSessionMode — skipping setMode');
          continue;
        }
        const modeId = step.resolveMode(initialModes as SessionMode[]);
        if (!modeId) {
          console.log('[fixture] No alternative mode found — skipping setMode');
          continue;
        }
        console.log(`[fixture] → setSessionMode modeId=${modeId}`);
        await agent.setSessionMode({ sessionId, modeId });
        recorder.record({ kind: 'mode_set', sessionId, modeId });
      }
    }

    console.log('\n[fixture] Closing session…');
    try {
      await agent.closeSession?.({ sessionId });
    } catch (e) {
      console.warn('[fixture] closeSession error (non-fatal):', e);
    }
  } finally {
    disposeClient();
    await scope.dispose();
    if (worktreePath) removeWorktree(worktreePath);

    console.log(`\n[fixture] Saving transcript to ${outPath}…`);
    await recorder.save(outPath);
    console.log(`[fixture] Done. ${recorder.events.length} events recorded.`);
  }
}

// Per-provider defaults applied when the provider is selected via --<id> flag.
const PROVIDER_DEFAULTS: Record<string, { model?: string | null }> = {
  claude: { model: 'claude-sonnet-5' },
  codex: { model: null },
};

function parseArgs(): TranscriptOptions {
  const args = process.argv.slice(2);
  const get = (flag: string): string | undefined => {
    const i = args.indexOf(flag);
    return i !== -1 ? args[i + 1] : undefined;
  };

  // Accept --<providerId> as shorthand (e.g. --claude, --codex).
  // The first unknown boolean flag (starts with -- but has no value) is treated
  // as the provider id.
  let providerId = get('--provider') ?? process.env['EMDASH_FIXTURE_PROVIDER'];

  if (!providerId) {
    const shorthand = args.find(
      (a) =>
        a.startsWith('--') &&
        !a.includes('=') &&
        !['--provider', '--model', '--cwd', '--out'].includes(a) &&
        args[args.indexOf(a) - 1] !== '--provider' &&
        args[args.indexOf(a) - 1] !== '--model' &&
        args[args.indexOf(a) - 1] !== '--cwd' &&
        args[args.indexOf(a) - 1] !== '--out'
    );
    if (shorthand) providerId = shorthand.slice(2);
  }

  providerId ??= 'claude';

  const defaults = PROVIDER_DEFAULTS[providerId] ?? {};
  const model = get('--model') ?? process.env['EMDASH_FIXTURE_MODEL'] ?? defaults.model ?? null;
  const cwd = get('--cwd') ?? process.env['EMDASH_FIXTURE_CWD'];
  const out = get('--out') ?? process.env['EMDASH_FIXTURE_OUT'];

  return { providerId, model, cwd, out };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const opts = parseArgs();
  console.log('[fixture] Starting ACP transcript capture:', opts);
  runAcpTranscript(opts).catch((e) => {
    console.error('[fixture] Fatal error:', e);
    process.exit(1);
  });
}
