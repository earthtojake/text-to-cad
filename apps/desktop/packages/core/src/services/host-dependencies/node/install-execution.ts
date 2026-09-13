import { err, ok, type Result } from '@emdash/shared';
import type { Logger } from '@emdash/shared/logger';
import { formatCommandLine } from '#primitives/exec/api';
import type { IExecutionContext } from '#primitives/exec/api';
import type {
  DependencyId,
  ElevationPolicy,
  HostDependencyDefinition,
  HostDependencyError,
  HostDependencySelection,
  HostDependencyView,
  HostElevation,
  InstallCommandOption,
  InstallMethod,
  PathCandidate,
  PermissionDeniedError,
  Platform,
} from '#primitives/host-dependencies/api';
import {
  probeHostElevation,
  resolveCommandPath,
} from '#services/host-dependencies/api/runtime/probe';

export type InstallCommandKind = 'install' | 'update';
export type InstallCommandMode = 'plain' | 'sudo' | 'sudo-interactive';

export type CommandExecutionResult =
  | { success: true }
  | { success: false; exitCode: number | null; message?: string };

export type InstallFailureContext = {
  id: DependencyId;
  command: string;
  commandKind: InstallCommandKind;
  elevation: ElevationPolicy;
  elevated: boolean;
  hostElevation: HostElevation | null;
};

export type PreparedInstallCommand = InstallFailureContext & {
  option: InstallCommandOption;
};

export type InstallCommandInvocation = {
  command: string;
  args: string[];
  preview: string;
};

export function buildInstallCommandInvocation(
  command: string,
  mode: InstallCommandMode,
  platform: NodeJS.Platform = process.platform
): InstallCommandInvocation {
  if (platform === 'win32') {
    const invocation = { command: 'cmd.exe', args: ['/d', '/s', '/c', command] };
    return {
      ...invocation,
      preview: formatCommandLine(invocation, 'windows-cmd'),
    };
  }

  const invocation =
    mode === 'sudo'
      ? { command: 'sudo', args: ['-n', '-H', '/bin/sh', '-c', command] }
      : mode === 'sudo-interactive'
        ? { command: 'sudo', args: ['/bin/sh', '-c', command] }
        : { command: '/bin/sh', args: ['-c', command] };
  return { ...invocation, preview: formatCommandLine(invocation, 'posix') };
}

export function isPermissionDeniedOutput(output: string): boolean {
  return /\b(?:EACCES|EPERM)\b|permission denied|operation not permitted/iu.test(output);
}

export type ElevationDecision =
  | { success: true; elevated: boolean; hostElevation: HostElevation | null }
  | { success: false; message: string; hostElevation: HostElevation | null };

export async function resolveElevationDecision(
  policy: ElevationPolicy,
  elevate: boolean,
  exec: IExecutionContext
): Promise<ElevationDecision> {
  if (policy === 'never' && !elevate) {
    return { success: true, elevated: false, hostElevation: null };
  }

  // Execution intentionally re-probes `sudo -n` instead of trusting a potentially stale snapshot.
  const hostElevation = await probeHostElevation(exec);
  if (elevate && policy === 'never') {
    return {
      success: false,
      message: 'This install method does not allow administrator elevation.',
      hostElevation,
    };
  }
  if (elevate && hostElevation !== 'root' && hostElevation !== 'passwordless-sudo') {
    return {
      success: false,
      message: 'Passwordless sudo is not available on this host.',
      hostElevation,
    };
  }
  if (policy === 'always' && hostElevation === 'unavailable') {
    return {
      success: false,
      message: 'This command requires administrator privileges on this host.',
      hostElevation,
    };
  }

  return {
    success: true,
    elevated: hostElevation === 'passwordless-sudo' && (policy === 'always' || elevate),
    hostElevation,
  };
}

export function permissionDeniedError({
  id,
  command,
  commandKind,
  output = '',
  exitCode,
  hostElevation,
  message,
}: {
  id: DependencyId;
  command: string;
  commandKind: InstallCommandKind;
  output?: string;
  exitCode?: number | null;
  hostElevation: HostElevation | null;
  message?: string;
}): PermissionDeniedError {
  return {
    type: 'permission-denied',
    id,
    message:
      message ??
      `${commandKind === 'update' ? 'Updating' : 'Installing'} ${id} needs administrator privileges.`,
    output,
    exitCode: exitCode ?? null,
    canRetryWithSudo: hostElevation === 'passwordless-sudo',
    elevatedCommand: buildInstallCommandInvocation(command, 'sudo').preview,
    interactiveCommand: buildInstallCommandInvocation(command, 'sudo-interactive').preview,
    command,
  };
}

export function installExecutionError(
  context: InstallFailureContext,
  execution: Extract<CommandExecutionResult, { success: false }>,
  output: string,
  logger?: Logger
): HostDependencyError {
  if (
    context.elevation === 'on-failure' &&
    !context.elevated &&
    // `null` denotes Windows, where sudo classification and guidance are intentionally off.
    context.hostElevation !== null &&
    isPermissionDeniedOutput(output)
  ) {
    return permissionDeniedError({
      id: context.id,
      command: context.command,
      commandKind: context.commandKind,
      output,
      exitCode: execution.exitCode,
      hostElevation: context.hostElevation,
    });
  }
  logger?.error(`Host dependency ${context.commandKind} command failed`, {
    id: context.id,
    command: context.command,
    exitCode: execution.exitCode ?? null,
    output,
  });
  return {
    type: 'command-failed',
    message:
      execution.message ??
      `${context.commandKind === 'update' ? 'Update' : 'Install'} command exited with code ${execution.exitCode ?? 'unknown'}`,
    output,
    exitCode: execution.exitCode ?? null,
  };
}

export function installOptionsForPlatform(
  definition: HostDependencyDefinition,
  platform: Platform = currentPlatform()
): InstallCommandOption[] {
  return definition.installCommands?.[platform] ?? [];
}

export function selectInstallOption(
  options: InstallCommandOption[],
  method: InstallMethod | undefined
): InstallCommandOption | undefined {
  if (method) return options.find((option) => option.method === method);
  return options.find((option) => option.recommended) ?? options[0];
}

export async function resolveInstallerTool(
  method: InstallMethod,
  exec: IExecutionContext
): Promise<{ found: boolean; label: string } | null> {
  const candidates = installerToolCandidates(method);
  if (candidates.length === 0) return null;

  for (const candidate of candidates) {
    const resolved = await resolveCommandPath(candidate, exec);
    if (resolved) return { found: true, label: candidate };
  }

  return { found: false, label: candidates.join(' or ') };
}

export function installerToolCandidates(method: InstallMethod): string[] {
  switch (method) {
    case 'homebrew':
      return ['brew'];
    case 'winget':
      return ['winget'];
    case 'powershell':
      return ['pwsh', 'powershell'];
    case 'npm':
      return ['npm'];
    case 'apt':
      return ['apt-get'];
    case 'curl':
      return ['curl'];
    case 'pip':
      return ['pip', 'pip3'];
    case 'cargo':
      return ['cargo'];
    case 'installer-macos':
    case 'installer-windows':
    case 'installer-linux':
    case 'other':
      return [];
  }
}

export function currentPlatform(platform: NodeJS.Platform = process.platform): Platform {
  if (platform === 'darwin') return 'macos';
  if (platform === 'win32') return 'windows';
  return 'linux';
}

export function resolveSelection(
  id: string,
  selection: HostDependencySelection,
  candidates: PathCandidate[]
): Result<NonNullable<HostDependencyView['resolved']>, HostDependencyError> {
  if (selection?.kind === 'path') {
    const candidate = candidates.find(
      (candidate) => candidate.path === selection.path || candidate.realpath === selection.path
    );
    if (!candidate) return err({ type: 'stale-selection', id, path: selection.path });
    return ok({
      id,
      command: candidate.command,
      path: candidate.path,
      realpath: candidate.realpath,
      source: { kind: 'path', path: selection.path },
    });
  }
  const first = candidates[0];
  if (!first) return err({ type: 'missing', id });
  return ok({
    id,
    command: first.command,
    path: first.path,
    realpath: first.realpath,
    source: { kind: 'auto' },
  });
}
