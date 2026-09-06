import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { mementosDomain, mementosWireContract } from './wire-contract';

export type MementosWireClient = ContractClient<typeof mementosWireContract>;

export function getMementosWireClient(): Promise<MementosWireClient> {
  return domainClient<MementosWireClient>(mementosDomain, mementosWireContract);
}
