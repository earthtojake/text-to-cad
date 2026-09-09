import { hostRef, LOCAL_HOST_REF, type HostRef } from '@emdash/core/primitives/host/api';
import type { RuntimeResolveError } from '@emdash/core/services/runtime-broker/api';
import type { Result } from '@emdash/shared';
import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { agentsContract, agentsDomain } from '../contract';

export type AgentsRpcClient = ContractClient<typeof agentsContract>;

export function getAgentsClient(): Promise<AgentsRpcClient> {
  return domainClient<AgentsRpcClient>(agentsDomain, agentsContract);
}

export async function unwrapAgentsResult<T>(
  result: Promise<Result<T, RuntimeResolveError>>
): Promise<T> {
  const resolved = await result;
  if (!resolved.success) throw resolved.error;
  return resolved.data;
}

export function hostRefFromConnectionId(connectionId?: string): HostRef {
  return connectionId ? hostRef('remote', connectionId) : LOCAL_HOST_REF;
}
