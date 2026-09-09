import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { catalogDomain, catalogWireContract } from '../wire-contract';

export type CatalogClient = ContractClient<typeof catalogWireContract>;

export function getCatalogClient(): Promise<CatalogClient> {
  return domainClient<CatalogClient>(catalogDomain, catalogWireContract);
}
