import { ok, type Result } from '@emdash/shared';
import type { BlobDownloadHandle, WireFile } from '../api/blob-channel';
import type { ContractClient } from '../api/client';
import type { CallMeta, Controller } from '../api/controller';
import {
  isEndpointDef,
  type Contract,
  type ContractDefinitions,
  type DownloadFileEndpointDef,
  type DownloadFileError,
  type DownloadFileInput,
  type DownloadFileMeta,
  type EndpointDef,
  type EndpointInput,
  type EndpointOutput,
  type UploadFileEndpointDef,
  type UploadFileError,
  type UploadFileInput,
  type UploadFileResult,
} from '../api/define';
import { rebindLiveClientHandle } from '../live/endpoint-kinds';
import { createController, type ContractImpl } from './controller';

export function forwardController<Defs extends ContractDefinitions>(
  contract: Contract<Defs>,
  client: ContractClient<Defs>
): Controller {
  return createController(contract, forwardContractImpl(contract, client));
}

/**
 * Builds a controller implementation that forwards every contract endpoint to an existing client.
 *
 * This is useful when a contract is mounted inside a larger aggregate contract. Live endpoint
 * handles are rebound to the mounted definitions while retaining their upstream client methods,
 * so a standalone `model` topic can be exposed as (for example) `git.model`.
 */
export function forwardContractImpl<Defs extends ContractDefinitions>(
  contract: Contract<Defs>,
  client: ContractClient<Defs>
): ContractImpl<Defs> {
  return buildForwardImpl(contract, client) as ContractImpl<Defs>;
}

function buildForwardImpl(
  definitions: ContractDefinitions,
  client: Record<string, unknown>
): Record<string, unknown> {
  const impl: Record<string, unknown> = {};

  for (const [name, def] of Object.entries(definitions)) {
    const clientEntry = client[name];
    if (!isEndpointDef(def)) {
      impl[name] = buildForwardImpl(def, requireRecord(clientEntry, name));
      continue;
    }

    impl[name] = createForwardEntry(def, clientEntry);
  }

  return impl;
}

function createForwardEntry(def: EndpointDef, clientEntry: unknown): unknown {
  switch (def.kind) {
    case 'procedure':
      return createProcedureForward(clientEntry);
    case 'uploadFile':
      return createUploadFileForward(clientEntry);
    case 'downloadFile':
      return createDownloadFileForward(clientEntry);
    case 'liveJob':
    case 'liveLog':
    case 'eventStream':
    case 'liveModel':
      return rebindLiveClientHandle(def, clientEntry);
  }
}

function createProcedureForward<Def extends EndpointDef>(
  clientEntry: unknown
): (input: EndpointInput<Def>, meta: CallMeta) => Promise<EndpointOutput<Def>> {
  const call = clientEntry as (
    input: EndpointInput<Def>,
    options?: Pick<CallMeta, 'signal'>
  ) => Promise<EndpointOutput<Def>>;
  return (input, meta) => call(input, meta);
}

function createUploadFileForward<Def extends UploadFileEndpointDef>(
  clientEntry: unknown
): (
  input: UploadFileInput<Def>,
  file: WireFile,
  meta: CallMeta
) => Promise<Result<UploadFileResult<Def>, UploadFileError<Def>>> {
  const upload = clientEntry as (
    input: UploadFileInput<Def>,
    file: WireFile,
    options?: Pick<CallMeta, 'signal'>
  ) => Promise<Result<UploadFileResult<Def>, UploadFileError<Def>>>;
  return (input, file, meta) => upload(input, file, meta);
}

function createDownloadFileForward<Def extends DownloadFileEndpointDef>(
  clientEntry: unknown
): (
  input: DownloadFileInput<Def>,
  meta: CallMeta
) => Promise<
  Result<{ meta: DownloadFileMeta<Def>; source: AsyncIterable<Uint8Array> }, DownloadFileError<Def>>
> {
  const download = clientEntry as (
    input: DownloadFileInput<Def>,
    options?: Pick<CallMeta, 'signal'>
  ) => Promise<Result<BlobDownloadHandle<DownloadFileMeta<Def>>, DownloadFileError<Def>>>;
  return async (input, meta) => {
    const result = await download(input, meta);
    if (!result.success) return result;
    return ok({ meta: result.data.meta, source: result.data.chunks() });
  };
}

function requireRecord(value: unknown, name: string): Record<string, unknown> {
  if (typeof value === 'object' && value !== null && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }

  throw new Error(`Cannot forward nested contract '${name}' from a non-object client entry`);
}
