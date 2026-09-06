import type { HostRef } from '@emdash/core/primitives/host/api';
import {
  isRuntimeResolveError,
  runtimeHostIdentityLost,
  runtimeHostUnavailable,
  type RuntimeResolveError,
  type RuntimeUnavailableReason,
} from '@emdash/core/primitives/runtime-resolution/api';
import { SshConnectionNotFoundError } from '@core/primitives/ssh/api';
import type { HostPreparingPhase } from '../api';
import { WorkspaceServerProtocolError, WorkspaceServerProvisionError } from './workspace-server';

export function translateHostPreparationError(
  host: HostRef,
  phase: HostPreparingPhase,
  error: unknown
): RuntimeResolveError {
  if (isRuntimeResolveError(error)) return error;
  if (hasCause(error, SshConnectionNotFoundError)) {
    return runtimeHostIdentityLost(host, 'Host identity is no longer configured');
  }
  if (error instanceof WorkspaceServerProtocolError) {
    return unavailable(
      host,
      error.details.action === 'upgrade-client'
        ? 'protocol-upgrade-client'
        : 'protocol-upgrade-server'
    );
  }
  if (error instanceof WorkspaceServerProvisionError) {
    if (
      error.code === 'protocol-incompatible' &&
      error.cause instanceof WorkspaceServerProtocolError
    ) {
      return unavailable(
        host,
        error.cause.details.action === 'upgrade-client'
          ? 'protocol-upgrade-client'
          : 'protocol-upgrade-server'
      );
    }
    return unavailable(
      host,
      error.code === 'protocol-incompatible' ? 'runtime-unavailable' : error.code
    );
  }
  return unavailable(host, phase === 'connecting' ? 'connection-failed' : 'runtime-unavailable');
}

function hasCause<TError extends Error>(
  error: unknown,
  constructor: abstract new (...args: never[]) => TError
): boolean {
  const seen = new Set<unknown>();
  let current = error;
  while (current instanceof Error && !seen.has(current)) {
    if (current instanceof constructor) return true;
    seen.add(current);
    current = current.cause;
  }
  return false;
}

function unavailable(host: HostRef, reason: RuntimeUnavailableReason): RuntimeResolveError {
  return runtimeHostUnavailable(host, reason, messageFor(reason));
}

function messageFor(reason: RuntimeUnavailableReason): string {
  switch (reason) {
    case 'offline':
      return 'Host is offline';
    case 'connection-failed':
      return 'Host connection failed';
    case 'daemon-start-failed':
      return 'Host runtime could not start';
    case 'artifact-download-failed':
      return 'Host runtime download failed';
    case 'install-failed':
      return 'Host runtime installation failed';
    case 'unsupported-platform':
      return 'Host platform is not supported';
    case 'protocol-upgrade-client':
      return 'The desktop app must be updated for this Host';
    case 'protocol-upgrade-server':
      return 'The Host runtime must be updated';
    case 'runtime-unavailable':
      return 'Host runtime is unavailable';
  }
}
