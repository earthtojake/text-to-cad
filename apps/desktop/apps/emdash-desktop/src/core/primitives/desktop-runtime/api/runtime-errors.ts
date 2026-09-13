import { hostRef, type HostRef } from '@emdash/core/primitives/host/api';
import {
  runtimeHostNotConfigured,
  runtimeHostUnavailable,
  type RuntimeResolveError,
} from '@emdash/core/primitives/runtime-resolution/api';

export type DesktopRuntimeCapability = 'host-dependencies' | 'projects' | 'workspaces';

const CAPABILITY_UNAVAILABLE_MESSAGES: Record<DesktopRuntimeCapability, string> = {
  'host-dependencies': 'Remote host dependencies require the workspace server.',
  projects: 'Remote projects require the workspace server and are not supported by this build',
  workspaces: 'Remote workspaces require the workspace server and are not supported by this build',
};

export function remoteRuntimeUnavailable(
  connectionId: string,
  capability: DesktopRuntimeCapability
): RuntimeResolveError {
  return runtimeHostUnavailable(
    hostRef('remote', connectionId),
    CAPABILITY_UNAVAILABLE_MESSAGES[capability]
  );
}

export function runtimeCapabilityNotConfigured(
  host: HostRef,
  capability: DesktopRuntimeCapability
): RuntimeResolveError {
  return runtimeHostNotConfigured(host, CAPABILITY_UNAVAILABLE_MESSAGES[capability]);
}
