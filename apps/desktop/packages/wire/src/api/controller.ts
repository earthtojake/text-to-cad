import type { PendingLease, Result, Unsubscribe } from '@emdash/shared';
import { markDownloadFileOpen, type BlobSource, type WireFile } from './blob-channel';
import type { LiveSource } from './channel';
import type {
  Contract,
  ContractDefinitions,
  DownloadFileEndpointDef,
  DownloadFileError,
  DownloadFileInput,
  DownloadFileMeta,
  EndpointInput,
  EndpointOutput,
  ProcedureDef,
  UploadFileEndpointDef,
  UploadFileError,
  UploadFileInput,
  UploadFileResult,
} from './define';
import { isEndpointDef } from './define';
import type { LiveEndpointKinds, LiveTopicBinding } from './endpoint-kinds';
import type { WireFileMeta } from './protocol';
import { WireError } from './protocol';
import { splitTopic } from './topics';
import { applyValidation, defaultValidatePolicy, type ValidatePolicy } from './validation';

export type CallMeta = {
  signal?: AbortSignal;
  uploadFile?: WireFile;
};

export type Controller = {
  call(path: string, input: unknown, meta?: CallMeta): Promise<unknown>;
  resolveLive(topic: string): LiveSource | null;
  acquireLive(topic: string): PendingLease<LiveSource> | null;
  dispose?(): Promise<void>;
};

export function isController(value: unknown): value is Controller {
  return (
    typeof value === 'object' &&
    value !== null &&
    typeof (value as Controller).call === 'function' &&
    typeof (value as Controller).resolveLive === 'function' &&
    typeof (value as Controller).acquireLive === 'function'
  );
}

export type ProcedureHandler<Def extends ProcedureDef = ProcedureDef> = (
  input: EndpointInput<Def>,
  meta: CallMeta
) => Promise<EndpointOutput<Def>> | EndpointOutput<Def>;

export type DownloadFileImpl<Def extends DownloadFileEndpointDef> = (
  input: DownloadFileInput<Def>,
  meta: CallMeta
) =>
  | Promise<Result<{ meta: DownloadFileMeta<Def>; source: BlobSource }, DownloadFileError<Def>>>
  | Result<{ meta: DownloadFileMeta<Def>; source: BlobSource }, DownloadFileError<Def>>;

export type UploadFileImpl<Def extends UploadFileEndpointDef> = (
  input: UploadFileInput<Def>,
  file: WireFile,
  meta: CallMeta
) =>
  | Promise<Result<UploadFileResult<Def>, UploadFileError<Def>>>
  | Result<UploadFileResult<Def>, UploadFileError<Def>>;

export type BuildControllerOptions = {
  /** The single internal live endpoint-kind dispatch table. */
  liveEndpoints: LiveEndpointKinds;
  /**
   * Contract validation policy. Defaults to the environment rule: `'full'`
   * (inputs + outputs) outside production, `'inputs'` in production.
   */
  validate?: ValidatePolicy;
};

/**
 * Core controller engine. Handles everything generic on the wire itself and
 * delegates live endpoint kinds to the supplied dispatch table. The public
 * `createController` wrapper injects the table.
 */
export function buildController<Defs extends ContractDefinitions>(
  contract: Contract<Defs>,
  impl: unknown,
  options: BuildControllerOptions
): Controller {
  return applyValidation(
    contract,
    assembleController(contract, impl, options.liveEndpoints),
    options.validate ?? defaultValidatePolicy()
  );
}

function assembleController(
  contract: ContractDefinitions,
  impl: unknown,
  liveEndpoints: LiveEndpointKinds
): Controller {
  const liveEntries = new Map<string, LiveTopicBinding>();
  const procedureEntries = new Map<string, (input: unknown, meta: CallMeta) => Promise<unknown>>();
  const disposables: Array<() => Promise<void>> = [];

  collectContractEntries(contract, impl as Record<string, unknown>, []);

  function collectContractEntries(
    definitions: ContractDefinitions,
    impl: Record<string, unknown> | undefined,
    prefix: string[]
  ): void {
    for (const [name, def] of Object.entries(definitions)) {
      const fullPath = [...prefix, name].join('.');
      const entryImpl = impl?.[name];
      if (!isEndpointDef(def)) {
        collectContractEntries(
          def,
          isRecord(entryImpl) ? (entryImpl as Record<string, unknown>) : undefined,
          [...prefix, name]
        );
        continue;
      }

      switch (def.kind) {
        case 'procedure': {
          const handler = entryImpl as ((input: unknown, meta: CallMeta) => unknown) | undefined;
          if (!handler) break;
          procedureEntries.set(fullPath, async (input, meta) => {
            return await handler(input, meta);
          });
          break;
        }
        case 'downloadFile': {
          const handler = entryImpl as DownloadFileImpl<DownloadFileEndpointDef> | undefined;
          if (!handler) break;
          procedureEntries.set(fullPath, async (input, meta) => {
            const output = await handler(input, meta);
            if (!output.success) {
              return output;
            }
            return {
              success: true,
              data: markDownloadFileOpen(output.data.meta as WireFileMeta, output.data.source),
            };
          });
          break;
        }
        case 'uploadFile': {
          const handler = entryImpl as UploadFileImpl<UploadFileEndpointDef> | undefined;
          if (!handler) break;
          procedureEntries.set(fullPath, async (input, meta) => {
            const uploadFile = meta.uploadFile;
            if (!uploadFile) {
              throw new WireError(
                'HANDLER_ERROR',
                `Upload file '${fullPath}' requires a file payload`
              );
            }
            validateUploadFileEnvelope(def, uploadFile);
            return await handler(input, limitUploadFile(uploadFile, def.maxSize), meta);
          });
          break;
        }
        case 'liveLog':
        case 'eventStream':
        case 'liveJob':
        case 'liveModel': {
          const binding = liveEndpoints.bindEndpoint(def, entryImpl, fullPath);
          for (const topic of binding.topics) liveEntries.set(topic.id, topic);
          for (const procedure of binding.procedures ?? []) {
            procedureEntries.set(procedure.path, procedure.handler);
          }
          if (binding.dispose) disposables.push(binding.dispose);
          break;
        }
      }
    }
  }

  return {
    async call(path, input, meta = {}) {
      const handler = procedureEntries.get(path);
      if (!handler) throw new WireError('UNKNOWN_PROCEDURE', `Unknown procedure '${path}'`);
      return await handler(input, meta);
    },
    resolveLive(topic) {
      const { refId, rawKey } = splitTopic(topic);
      const entry = liveEntries.get(refId);
      if (!entry?.resolve) return null;
      const result = entry.resolve(rawKey);
      if (result == null) return missingLiveSource(`Unknown live topic '${topic}'`);
      if (isPromiseLike(result)) return awaitedLiveSource(result, `Unknown live topic '${topic}'`);
      return result;
    },
    acquireLive(topic) {
      const { refId, rawKey } = splitTopic(topic);
      const entry = liveEntries.get(refId);
      if (!entry) return null;
      if (entry.acquire) return entry.acquire(rawKey);
      const result = entry.resolve?.(rawKey);
      if (result == null)
        return immediateLiveSourceLease(missingLiveSource(`Unknown live topic '${topic}'`));
      if (isPromiseLike(result)) {
        const resolved = result.then(
          (s) => s ?? missingLiveSource(`Unknown live topic '${topic}'`)
        );
        resolved.catch(() => {});
        return { ready: async () => await resolved, release: async () => {} };
      }
      return immediateLiveSourceLease(result);
    },
    async dispose() {
      await Promise.all(disposables.map((dispose) => dispose()));
    },
  };
}

function immediateLiveSourceLease(source: LiveSource): PendingLease<LiveSource> {
  return {
    ready: async () => source,
    release: async () => {},
  };
}

function limitUploadFile(file: WireFile, maxSize: number | undefined): WireFile {
  if (maxSize === undefined) return file;
  return {
    ...file,
    stream() {
      return (async function* () {
        const iterator = file.stream()[Symbol.asyncIterator]();
        let total = 0;
        try {
          for (;;) {
            const next = await iterator.next();
            if (next.done) return;
            const chunk = next.value;
            total += chunk.byteLength;
            if (total > maxSize) {
              file.cancel();
              throw new WireError(
                'CONTRACT_MISMATCH',
                `Upload file size exceeded maximum ${maxSize}`
              );
            }
            yield chunk;
          }
        } finally {
          await iterator.return?.();
        }
      })();
    },
    async bytes() {
      const chunks: Uint8Array[] = [];
      let total = 0;
      for await (const chunk of this.stream()) {
        chunks.push(chunk);
        total += chunk.byteLength;
      }
      const out = new Uint8Array(total);
      let offset = 0;
      for (const chunk of chunks) {
        out.set(chunk, offset);
        offset += chunk.byteLength;
      }
      return out;
    },
  };
}

function validateUploadFileEnvelope(def: UploadFileEndpointDef, file: WireFile): void {
  if (def.accept && !def.accept.includes(file.mimeType)) {
    throw new WireError(
      'CONTRACT_MISMATCH',
      `Upload file MIME type '${file.mimeType}' is not accepted`
    );
  }
  if (def.maxSize !== undefined && file.size !== undefined && file.size > def.maxSize) {
    throw new WireError(
      'CONTRACT_MISMATCH',
      `Upload file size ${file.size} exceeds maximum ${def.maxSize}`
    );
  }
}

function missingLiveSource(message: string): LiveSource {
  return {
    snapshot() {
      throw new WireError('NOT_FOUND', message);
    },
    subscribe(): Unsubscribe {
      throw new WireError('NOT_FOUND', message);
    },
  };
}

function awaitedLiveSource(
  pending: Promise<LiveSource | null | undefined>,
  missingMessage: string
): LiveSource {
  const resolved = pending.then((s) => s ?? missingLiveSource(missingMessage));
  resolved.catch(() => {});
  return {
    async snapshot() {
      return await (await resolved).snapshot();
    },
    async subscribe(callback, options) {
      return await (await resolved).subscribe(callback, options);
    },
  };
}

function isPromiseLike(value: unknown): value is PromiseLike<LiveSource | null | undefined> {
  return typeof (value as PromiseLike<unknown>)?.then === 'function';
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
