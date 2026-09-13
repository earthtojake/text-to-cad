import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { terminalsContract, terminalsDomain } from '../wire-contract';

export type TerminalsClient = ContractClient<typeof terminalsContract>;

export function getTerminalsClient(): Promise<TerminalsClient> {
  return domainClient<TerminalsClient>(terminalsDomain, terminalsContract);
}
