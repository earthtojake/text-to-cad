import type { ContractClient } from '@emdash/wire/rpc';
import { domainClient } from '@core/primitives/wire/browser/connection';
import { editorContract, editorDomain } from '../contract';

export type EditorClient = ContractClient<typeof editorContract>;

export function getEditorClient(): Promise<EditorClient> {
  return domainClient<EditorClient>(editorDomain, editorContract);
}
