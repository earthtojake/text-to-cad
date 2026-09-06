import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { repositoryContract, repositoryDomain } from './contract';

export type RepositoryClient = ContractClient<typeof repositoryContract>;

export function getRepositoryClient(): Promise<RepositoryClient> {
  return domainClient<RepositoryClient>(repositoryDomain, repositoryContract);
}
