import type { ContractClient } from '@emdash/wire/rpc';
import { skillsContract, skillsDomain } from '@core/features/skills/api/contract';
import { domainClient } from '@core/primitives/wire/browser/connection';

export type SkillsRpcClient = ContractClient<typeof skillsContract>;

export function getSkillsClient(): Promise<SkillsRpcClient> {
  return domainClient<SkillsRpcClient>(skillsDomain, skillsContract);
}
