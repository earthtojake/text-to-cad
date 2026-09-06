import type { SshConfigHost } from '@core/primitives/ssh/api';

export type MachineAuthType = 'password' | 'key' | 'agent';

export function suggestedAuthTypeForSshConfigHost(host: SshConfigHost): MachineAuthType {
  if (host.identityAgent) return 'agent';
  if (host.identityFile) return 'key';
  return 'agent';
}
