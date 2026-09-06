export const TERMINAL_SHELL_IDS = [
  'system',
  'bash',
  'cmd',
  'fish',
  'powershell',
  'pwsh',
  'wsl',
  'zsh',
] as const;

export const RUNTIME_TERMINAL_SHELL_IDS = [
  'bash',
  'cmd',
  'csh',
  'dash',
  'fish',
  'ksh',
  'powershell',
  'pwsh',
  'sh',
  'tcsh',
  'wsl',
  'zsh',
] as const;

export type TerminalShellId = (typeof TERMINAL_SHELL_IDS)[number];
export type ExplicitTerminalShellId = Exclude<TerminalShellId, 'system'>;
export type RuntimeTerminalShellId = (typeof RUNTIME_TERMINAL_SHELL_IDS)[number];
export type TerminalShellFamily = 'posix' | 'csh' | 'windows-cmd' | 'powershell' | 'wsl';

export type TerminalShellAvailability = {
  id: TerminalShellId;
  label: string;
  isSystemDefault: boolean;
  available: boolean;
  reason?: string;
};

const CSH_SHELLS = new Set<string>(['csh', 'tcsh']);
const BASIC_INTERACTIVE_SHELLS = new Set<string>(['csh', 'dash', 'sh', 'tcsh']);

export function terminalShellBasename(shell: string): string {
  return shell.split(/[\\/]/).pop()?.toLowerCase() ?? '';
}

export function isExplicitTerminalShellId(shell: string): shell is ExplicitTerminalShellId {
  return TERMINAL_SHELL_IDS.includes(shell as TerminalShellId) && shell !== 'system';
}

export function isRuntimeTerminalShellId(shell: string): shell is RuntimeTerminalShellId {
  return RUNTIME_TERMINAL_SHELL_IDS.includes(shell as RuntimeTerminalShellId);
}

export function isCshShell(shell: string): boolean {
  return CSH_SHELLS.has(terminalShellBasename(shell));
}

export function terminalShellFamily(shell: string): TerminalShellFamily {
  const base = terminalShellBasename(shell);
  if (base === 'cmd' || base === 'cmd.exe') return 'windows-cmd';
  if (base === 'powershell' || base === 'powershell.exe' || base === 'pwsh' || base === 'pwsh.exe')
    return 'powershell';
  if (base === 'wsl' || base === 'wsl.exe') return 'wsl';
  if (CSH_SHELLS.has(base)) return 'csh';
  return 'posix';
}

export function terminalInteractiveShellArgs(shell: string): string[] {
  const family = terminalShellFamily(shell);
  if (family === 'windows-cmd' || family === 'powershell' || family === 'wsl') return [];
  return BASIC_INTERACTIVE_SHELLS.has(terminalShellBasename(shell)) ? ['-i'] : ['-il'];
}

export function terminalCommandArgs(shell: string): string[] {
  switch (terminalShellFamily(shell)) {
    case 'windows-cmd':
      return ['/d', '/s', '/c'];
    case 'powershell':
      return ['-NoProfile', '-Command'];
    case 'wsl':
      return ['--exec', 'sh', '-lc'];
    case 'posix':
    case 'csh':
      return BASIC_INTERACTIVE_SHELLS.has(terminalShellBasename(shell)) ? ['-c'] : ['-lc'];
  }
}

export function terminalEnvCaptureArgs(shell: string): string[] | undefined {
  switch (terminalShellFamily(shell)) {
    case 'csh':
      return ['-i', '-c'];
    case 'posix':
      return BASIC_INTERACTIVE_SHELLS.has(terminalShellBasename(shell)) ? ['-ic'] : ['-ilc'];
    case 'windows-cmd':
    case 'powershell':
    case 'wsl':
      return undefined;
  }
}
