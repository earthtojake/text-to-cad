import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { sshContract, sshDomain } from './contract';

export type SshClient = ContractClient<typeof sshContract>;

export function getSshClient(): Promise<SshClient> {
  return domainClient<SshClient>(sshDomain, sshContract);
}
