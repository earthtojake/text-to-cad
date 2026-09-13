import fs from 'node:fs';
import path from 'node:path';
import {
  isRuntimeTerminalShellId,
  terminalCommandArgs,
  terminalEnvCaptureArgs,
  terminalInteractiveShellArgs,
  terminalShellBasename,
  terminalShellFamily,
  type ExplicitTerminalShellId,
  type ResolvedShellProfile,
  type RuntimeTerminalShellId,
  type TerminalShellAvailability,
  type TerminalShellId,
  type TerminalShellResolver,
} from '#primitives/terminal-shell/api';

export class ShellUnavailableError extends Error {
  constructor(
    readonly shell: TerminalShellId,
    message = `${shell} is not available on this host`
  ) {
    super(message);
    this.name = 'ShellUnavailableError';
  }
}

type FileExists = (candidate: string) => boolean;
type ReadDirNames = (candidate: string) => string[];

function isExecutable(filePath: string): boolean {
  try {
    fs.accessSync(filePath, fs.constants.X_OK);
    return fs.statSync(filePath).isFile();
  } catch {
    return false;
  }
}

function readDirNames(dirPath: string): string[] {
  try {
    return fs
      .readdirSync(dirPath, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .map((entry) => entry.name);
  } catch {
    return [];
  }
}

function pathDirs(env: NodeJS.ProcessEnv, platform: NodeJS.Platform): string[] {
  const rawPath =
    platform === 'win32' ? (env.Path ?? env.PATH ?? env.path ?? '') : (env.PATH ?? '');
  return rawPath
    .split(platform === 'win32' ? path.win32.delimiter : path.posix.delimiter)
    .filter(Boolean);
}

function windowsPathExts(env: NodeJS.ProcessEnv): string[] {
  const raw = env.PATHEXT ?? '.COM;.EXE;.BAT;.CMD';
  return raw
    .split(';')
    .map((ext) => ext.trim())
    .filter(Boolean)
    .map((ext) => (ext.startsWith('.') ? ext : `.${ext}`));
}

function findOnPath(
  shell: string,
  env: NodeJS.ProcessEnv,
  platform: NodeJS.Platform,
  fileExists: FileExists = isExecutable,
  isAllowed: (candidate: string) => boolean = () => true
): string | undefined {
  const pathApi = platform === 'win32' ? path.win32 : path.posix;
  if (pathApi.isAbsolute(shell) && isAllowed(shell) && fileExists(shell)) return shell;

  for (const dir of pathDirs(env, platform)) {
    const candidate = pathApi.join(dir, shell);
    if (isAllowed(candidate) && fileExists(candidate)) return candidate;

    if (platform === 'win32' && !path.extname(shell)) {
      for (const ext of windowsPathExts(env)) {
        const winCandidate = `${candidate}${ext}`;
        if (isAllowed(winCandidate) && fileExists(winCandidate)) return winCandidate;
      }
    }
  }

  return undefined;
}

function firstExisting(
  candidates: string[],
  fileExists: FileExists = isExecutable
): string | undefined {
  return candidates.find((candidate) => fileExists(candidate));
}

function compareVersionParts(a: number[], b: number[]): number {
  const len = Math.max(a.length, b.length);
  for (let i = 0; i < len; i += 1) {
    const diff = (a[i] ?? 0) - (b[i] ?? 0);
    if (diff !== 0) return diff;
  }
  return 0;
}

function powerShellVersionParts(name: string): number[] | null {
  const match = /^(\d+(?:\.\d+)*)(?:-.+)?$/.exec(name);
  if (!match) return null;
  return match[1].split('.').map((part) => Number(part));
}

function findLatestWindowsPwsh(
  env: NodeJS.ProcessEnv,
  fileExists: FileExists = isExecutable,
  readDirs: ReadDirNames = readDirNames
): string | undefined {
  const roots = [
    env.ProgramFiles,
    env.ProgramW6432,
    env.LOCALAPPDATA ? path.win32.join(env.LOCALAPPDATA, 'Microsoft') : undefined,
  ]
    .filter((root): root is string => Boolean(root))
    .map((root) => path.win32.join(root, 'PowerShell'));

  let best: { version: number[]; candidate: string } | undefined;
  for (const root of [...new Set(roots)]) {
    for (const dir of readDirs(root)) {
      const version = powerShellVersionParts(dir);
      if (!version) continue;
      const candidate = path.win32.join(root, dir, 'pwsh.exe');
      if (!fileExists(candidate)) continue;
      if (!best || compareVersionParts(version, best.version) > 0) {
        best = { version, candidate };
      }
    }
  }

  return best?.candidate ?? findOnPath('pwsh.exe', env, 'win32', fileExists);
}

function windowsSystemCommand(
  executable: string,
  env: NodeJS.ProcessEnv,
  fileExists: FileExists = isExecutable
): string | undefined {
  const systemRoot = env.SystemRoot ?? env.windir;
  const systemCandidate = systemRoot
    ? path.win32.join(systemRoot, 'System32', executable)
    : undefined;
  return firstExisting(systemCandidate ? [systemCandidate] : [], fileExists);
}

function isWindowsWslBashLauncher(candidate: string): boolean {
  const normalized = path.win32.normalize(candidate).toLowerCase();
  return (
    normalized.endsWith('\\windows\\system32\\bash.exe') ||
    normalized.endsWith('\\windows\\sysnative\\bash.exe') ||
    normalized.endsWith('\\windows\\syswow64\\bash.exe')
  );
}

function windowsGitBashCandidates(env: NodeJS.ProcessEnv): string[] {
  const roots = [
    env.ProgramFiles,
    env.ProgramW6432,
    env['ProgramFiles(x86)'],
    env.LOCALAPPDATA ? path.win32.join(env.LOCALAPPDATA, 'Programs') : undefined,
  ].filter((root): root is string => Boolean(root));

  const candidates: string[] = [];
  for (const root of [...new Set(roots)]) {
    const gitRoot = path.win32.join(root, 'Git');
    candidates.push(path.win32.join(gitRoot, 'bin', 'bash.exe'));
    candidates.push(path.win32.join(gitRoot, 'usr', 'bin', 'bash.exe'));
  }
  return candidates;
}

function findWindowsGitBash(
  env: NodeJS.ProcessEnv,
  fileExists: FileExists = isExecutable
): string | undefined {
  return (
    firstExisting(windowsGitBashCandidates(env), fileExists) ??
    findOnPath(
      'bash.exe',
      env,
      'win32',
      fileExists,
      (candidate) => !isWindowsWslBashLauncher(candidate)
    )
  );
}

function shellIdFromExecutable(
  executable: string,
  fallback: RuntimeTerminalShellId
): RuntimeTerminalShellId {
  const base = terminalShellBasename(executable).replace(/\.exe$/, '');
  return isRuntimeTerminalShellId(base) ? base : fallback;
}

function shellLabelFromExecutable(executable: string, fallback: RuntimeTerminalShellId): string {
  const base = terminalShellBasename(executable).replace(/\.exe$/, '');
  return base || fallback;
}

function localDefaultShell(platform: NodeJS.Platform, env: NodeJS.ProcessEnv): string {
  if (platform === 'win32') return env.ComSpec || 'C:\\Windows\\System32\\cmd.exe';
  return env.SHELL ?? (platform === 'darwin' ? '/bin/zsh' : '/bin/bash');
}

function resolveLocalExplicitShell(
  shell: ExplicitTerminalShellId,
  platform: NodeJS.Platform,
  env: NodeJS.ProcessEnv,
  fileExists?: FileExists,
  readDirs?: ReadDirNames
): string | undefined {
  if (platform === 'win32') {
    if (shell === 'cmd') return env.ComSpec || 'C:\\Windows\\System32\\cmd.exe';
    if (shell === 'powershell') return findOnPath('powershell.exe', env, platform, fileExists);
    if (shell === 'pwsh') return findLatestWindowsPwsh(env, fileExists, readDirs);
    if (shell === 'wsl') return windowsSystemCommand('wsl.exe', env, fileExists);
    if (shell === 'bash') return findWindowsGitBash(env, fileExists);
    return findOnPath(shell, env, platform, fileExists);
  }

  if (shell === 'cmd' || shell === 'powershell' || shell === 'pwsh' || shell === 'wsl') {
    return undefined;
  }
  return findOnPath(shell, env, platform, fileExists);
}

function explicitShellLabel(shell: TerminalShellId, platform: NodeJS.Platform): string {
  if (platform !== 'win32') return shell;
  switch (shell) {
    case 'bash':
      return 'Git Bash';
    case 'powershell':
      return 'PowerShell';
    case 'pwsh':
      return 'PowerShell 7';
    case 'wsl':
      return 'WSL';
    default:
      return shell;
  }
}

function buildProfile({
  id,
  resolvedShellId,
  executable,
  resolvedFromSystem,
  capturedEnv,
  remotePathLookup,
  shellForArgs = resolvedShellId,
}: {
  id: RuntimeTerminalShellId | 'target-default';
  resolvedShellId: RuntimeTerminalShellId;
  executable: string;
  resolvedFromSystem: boolean;
  capturedEnv?: Record<string, string>;
  remotePathLookup?: boolean;
  shellForArgs?: string;
}): ResolvedShellProfile {
  const family = terminalShellFamily(shellForArgs);
  return {
    id,
    resolvedShellId,
    resolvedFromSystem,
    executable,
    available: true,
    family,
    interactiveArgs: terminalInteractiveShellArgs(shellForArgs),
    commandArgs: terminalCommandArgs(shellForArgs),
    envCaptureArgs: terminalEnvCaptureArgs(shellForArgs),
    capturedEnv,
    remotePathLookup,
  };
}

export async function resolveTerminalShell({
  intent,
  platform = process.platform,
  env = process.env,
  fileExists,
  readDirNames: readDirs,
}: {
  intent: TerminalShellId;
  platform?: NodeJS.Platform;
  env?: NodeJS.ProcessEnv;
  fileExists?: FileExists;
  readDirNames?: ReadDirNames;
}): Promise<ResolvedShellProfile> {
  if (intent === 'system') {
    const executable = localDefaultShell(platform, env);
    const resolvedShellId = shellIdFromExecutable(executable, platform === 'win32' ? 'cmd' : 'sh');
    return buildProfile({
      id: 'target-default',
      resolvedShellId,
      executable,
      resolvedFromSystem: true,
      shellForArgs: executable,
    });
  }

  const executable = resolveLocalExplicitShell(intent, platform, env, fileExists, readDirs);
  if (!executable) throw new ShellUnavailableError(intent);
  return buildProfile({
    id: intent,
    resolvedShellId: intent,
    executable,
    resolvedFromSystem: false,
  });
}

export async function resolveTerminalShellWithSystemFallback({
  intent,
  platform = process.platform,
  env = process.env,
  fileExists,
  readDirNames: readDirs,
  onFallback,
}: {
  intent: TerminalShellId;
  platform?: NodeJS.Platform;
  env?: NodeJS.ProcessEnv;
  fileExists?: FileExists;
  readDirNames?: ReadDirNames;
  onFallback?: (error: ShellUnavailableError) => void;
}): Promise<ResolvedShellProfile> {
  try {
    return await resolveTerminalShell({
      intent,
      platform,
      env,
      fileExists,
      readDirNames: readDirs,
    });
  } catch (error) {
    if (intent === 'system' || !(error instanceof ShellUnavailableError)) {
      throw error;
    }
    onFallback?.(error);
    return await resolveTerminalShell({
      intent: 'system',
      platform,
      env,
      fileExists,
      readDirNames: readDirs,
    });
  }
}

export async function getLocalTerminalShellAvailability({
  platform = process.platform,
  env = process.env,
  fileExists,
  readDirNames: readDirs,
}: {
  platform?: NodeJS.Platform;
  env?: NodeJS.ProcessEnv;
  fileExists?: FileExists;
  readDirNames?: ReadDirNames;
} = {}): Promise<TerminalShellAvailability[]> {
  const targetDefaultShell = localDefaultShell(platform, env);
  const targetDefaultId = shellIdFromExecutable(
    targetDefaultShell,
    platform === 'win32' ? 'cmd' : 'sh'
  );
  return sortShellAvailability(
    shellIdsForLocalPlatform(platform)
      .filter((shell) => shell === 'system' || shell !== targetDefaultId)
      .map((shell) => {
        if (shell === 'system') {
          return {
            id: shell,
            label: shellLabelFromExecutable(targetDefaultShell, targetDefaultId),
            isSystemDefault: true,
            available: true,
          };
        }
        const executable = resolveLocalExplicitShell(shell, platform, env, fileExists, readDirs);
        return {
          id: shell,
          label: explicitShellLabel(shell, platform),
          isSystemDefault: false,
          available: executable !== undefined,
          reason: executable === undefined ? 'Not found on this machine' : undefined,
        };
      })
  );
}

function shellIdsForLocalPlatform(platform: NodeJS.Platform): TerminalShellId[] {
  if (platform === 'win32') return ['system', 'powershell', 'cmd', 'wsl', 'bash'];
  return ['system', 'zsh', 'bash', 'fish'];
}

function sortShellAvailability(entries: TerminalShellAvailability[]): TerminalShellAvailability[] {
  return [...entries].sort((a, b) => {
    if (a.id === 'system') return -1;
    if (b.id === 'system') return 1;
    if (a.available !== b.available) return a.available ? -1 : 1;
    return 0;
  });
}

/**
 * Builds a host-local {@link TerminalShellResolver}. Defaults bind to this
 * process's platform, environment, and filesystem, so the terminals runtime
 * resolves shells on whichever host it runs on.
 */
export function createNodeTerminalShellResolver(
  options: {
    platform?: NodeJS.Platform;
    env?: NodeJS.ProcessEnv;
    fileExists?: FileExists;
    readDirNames?: ReadDirNames;
  } = {}
): TerminalShellResolver {
  const platform = options.platform ?? process.platform;
  const env = options.env ?? process.env;
  return {
    resolveWithSystemFallback: ({ intent, onFallback }) =>
      resolveTerminalShellWithSystemFallback({
        intent,
        platform,
        env,
        fileExists: options.fileExists,
        readDirNames: options.readDirNames,
        onFallback: onFallback
          ? (error) => onFallback({ shell: error.shell, message: error.message })
          : undefined,
      }),
    getAvailability: () =>
      getLocalTerminalShellAvailability({
        platform,
        env,
        fileExists: options.fileExists,
        readDirNames: options.readDirNames,
      }),
  };
}
