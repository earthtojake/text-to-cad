import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { machinesContract, machinesDomain } from '../contract';

export type MachinesClient = ContractClient<typeof machinesContract>;

export function getMachinesClient(): Promise<MachinesClient> {
  return domainClient<MachinesClient>(machinesDomain, machinesContract);
}
