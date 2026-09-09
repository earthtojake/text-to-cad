import { isLocalHostRef, parseHostRef, sshConnectionIdOf } from '@emdash/core/primitives/host/api';
import type { HostReachabilityProbe } from '@core/primitives/ssh/api';

export function createHostReachabilityProbe(ssh: {
  isConnected(connectionId: string): boolean;
}): HostReachabilityProbe {
  return (hostRef) => {
    const parsed = parseHostRef(hostRef);
    if (isLocalHostRef(parsed)) return true;
    const connectionId = sshConnectionIdOf(parsed);
    return connectionId !== undefined && ssh.isConnected(connectionId);
  };
}
