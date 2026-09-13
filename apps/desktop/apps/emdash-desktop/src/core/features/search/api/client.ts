import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { searchContract, searchDomain } from './contract';

export type SearchClient = ContractClient<typeof searchContract>;

export function getSearchClient(): Promise<SearchClient> {
  return domainClient<SearchClient>(searchDomain, searchContract);
}
