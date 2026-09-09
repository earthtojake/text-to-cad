import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { filesDomain, filesWireContract } from '../contract';

export type FilesClient = ContractClient<typeof filesWireContract>;

export function getFilesClient(): Promise<FilesClient> {
  return domainClient<FilesClient>(filesDomain, filesWireContract);
}
