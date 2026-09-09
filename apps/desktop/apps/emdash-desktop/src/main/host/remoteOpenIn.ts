import { formatCommandLine, quoteArg } from '@emdash/core/primitives/exec/api';

type RemoteEditorScheme = 'vscode' | 'vscodium' | 'cursor' | 'zed';

export function buildRemoteSshAuthority(host: string, username: string): string {
  const normalizedHost = host.trim();
  if (!normalizedHost) return normalizedHost;

  // Keep host as-is when caller already included user info (for SSH aliases like user@host).
  if (normalizedHost.includes('@')) return normalizedHost;

  const normalizedUsername = username.trim();
  if (!normalizedUsername) return normalizedHost;

  return `${normalizedUsername}@${normalizedHost}`;
}

function encodeRemotePath(targetPath: string): string {
  const normalizedPath = targetPath.startsWith('/') ? targetPath : `/${targetPath}`;
  return normalizedPath.split('/').map(encodeURIComponent).join('/');
}

function splitSshAuthority(host: string, username: string): { hostName: string; user?: string } {
  const normalizedHost = host.trim();
  const atIndex = normalizedHost.lastIndexOf('@');
  if (atIndex > 0) {
    return {
      user: normalizedHost.slice(0, atIndex),
      hostName: normalizedHost.slice(atIndex + 1),
    };
  }

  const normalizedUsername = username.trim();
  return {
    hostName: normalizedHost,
    ...(normalizedUsername ? { user: normalizedUsername } : {}),
  };
}

function buildVsCodeRemoteAuthority(host: string, username: string): string {
  const { hostName, user } = splitSshAuthority(host, username);
  if (!user && /^[a-zA-Z0-9.:-]+$/.test(hostName) && !/[A-Z/\\+]/.test(hostName)) {
    return hostName;
  }

  return Buffer.from(
    JSON.stringify({
      hostName,
      ...(user ? { user } : {}),
    })
  ).toString('hex');
}

export function buildRemoteEditorUrl(
  scheme: RemoteEditorScheme,
  host: string,
  username: string,
  targetPath: string,
  port?: number | string
): string {
  const authority = buildRemoteSshAuthority(host, username);
  const vscodeAuthority = buildVsCodeRemoteAuthority(host, username);
  const zedAuthority = port && String(port) !== '22' ? `${authority}:${port}` : authority;
  const encodedTargetPath = encodeRemotePath(targetPath);

  switch (scheme) {
    case 'zed':
      return `zed://ssh/${zedAuthority}${encodedTargetPath}`;
    // VS Code-family editors resolve the SSH port via ~/.ssh/config, so the port
    // is intentionally omitted from the vscode-remote URL authority.
    default:
      return `${scheme}://vscode-remote/ssh-remote+${vscodeAuthority}${encodedTargetPath}`;
  }
}

type RemoteTerminalExecInput = {
  host: string;
  username: string;
  port: number | string;
  targetPath: string;
};

/**
 * Shell payload executed on the remote host after SSH connects.
 *
 * Goals:
 * - always start in the requested directory
 * - preserve current TERM only when host supports it (fallback for missing terminfo)
 * - keep session alive even when SHELL is unset/invalid by chaining shell fallbacks
 */
export function buildRemoteTerminalShellCommand(targetPath: string): string {
  return `cd ${quoteArg(targetPath, 'posix')} && (if command -v infocmp >/dev/null 2>&1 && [ -n "\${TERM:-}" ] && infocmp "\${TERM}" >/dev/null 2>&1; then :; else export TERM=xterm-256color; fi) && (exec "\${SHELL:-/bin/bash}" || exec /bin/bash || exec /bin/sh)`;
}

/**
 * Builds a single SSH command string for terminals that accept shell command text
 * (Terminal.app, iTerm2 via AppleScript, Warp URL cmd parameter).
 *
 * Command text is shell-escaped because these launchers execute through a shell.
 */
export function buildRemoteSshCommand(input: RemoteTerminalExecInput): string {
  const sshAuthority = buildRemoteSshAuthority(input.host, input.username);
  const remoteCommand = buildRemoteTerminalShellCommand(input.targetPath);
  return formatCommandLine(
    {
      command: 'ssh',
      args: [
        sshAuthority,
        '-o',
        'ControlMaster=no',
        '-o',
        'ControlPath=none',
        '-p',
        String(input.port),
        '-t',
        remoteCommand,
      ],
    },
    'posix'
  );
}

/**
 * Builds argv tokens for terminal remote SSH execution.
 *
 * We pass these tokens directly via child_process execFile/spawn (shell disabled), so host/port
 * are not shell-quoted here. The remote command itself is still shell-escaped because it is
 * parsed by the remote shell over SSH.
 */
export function buildRemoteTerminalExecArgs(input: RemoteTerminalExecInput): string[] {
  const sshAuthority = buildRemoteSshAuthority(input.host, input.username);
  const remoteCommand = buildRemoteTerminalShellCommand(input.targetPath);
  return [
    'ssh',
    sshAuthority,
    '-o',
    'ControlMaster=no',
    '-o',
    'ControlPath=none',
    '-p',
    String(input.port),
    '-t',
    remoteCommand,
  ];
}
