import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { mcpContract, mcpDomain } from '../contract';

export type McpRpcClient = ContractClient<typeof mcpContract>;

export function getMcpClient(): Promise<McpRpcClient> {
  return domainClient<McpRpcClient>(mcpDomain, mcpContract);
}
