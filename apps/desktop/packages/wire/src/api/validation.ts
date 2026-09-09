import { resultSchema } from '@emdash/shared';
import { z } from 'zod';
import { isDownloadFileOpenResult, markDownloadFileOpen } from './blob-channel';
import { liveCursorEntrySchema } from './channel';
import type { CallMeta, Controller } from './controller';
import type {
  Contract,
  ContractDefinitions,
  DownloadFileEndpointDef,
  EndpointDef,
  LiveModelDef,
  MutationDef,
} from './define';
import { isEndpointDef } from './define';
import type { WireFileMeta } from './protocol';
import { encodeTopic, splitTopic } from './topics';

export type ValidatePolicy = 'none' | 'inputs' | 'full';

/**
 * The one environment-sensitive validation default: full validation (inputs +
 * outputs) everywhere except production, inputs-only in production. Applies
 * identically to bare controllers, component instances, component workers, and
 * tests.
 */
// Bundlers statically replace `process.env.NODE_ENV` in browser builds; the
// structural declaration keeps this file free of node ambient types.
declare const process: { env: Record<string, string | undefined> };

export function defaultValidatePolicy(
  env: Record<string, string | undefined> = process.env
): ValidatePolicy {
  return env.NODE_ENV === 'production' ? 'inputs' : 'full';
}

type ProcedureValidator = {
  parseInput(input: unknown): unknown;
  parseOutput?(output: unknown): unknown;
};

const jobKeySchema = z.object({ jobId: z.string() });
const jobStartOutputSchema = z.object({ jobId: z.string() });

export function applyValidation<Defs extends ContractDefinitions>(
  contract: Contract<Defs>,
  controller: Controller,
  policy: ValidatePolicy
): Controller {
  if (policy === 'none') return controller;

  const procedures = new Map<string, ProcedureValidator>();
  const liveKeys = new Map<string, z.ZodTypeAny>();

  collectContractValidators(contract, []);

  return {
    async call(path: string, input: unknown, meta?: CallMeta) {
      const validator = procedures.get(path);
      if (!validator) return await controller.call(path, input, meta);

      const parsedInput = validator.parseInput(input);
      const output = await controller.call(path, parsedInput, meta);
      return policy === 'full' && validator.parseOutput ? validator.parseOutput(output) : output;
    },
    resolveLive(topic: string) {
      const { refId, rawKey } = splitTopic(topic);
      const keySchema = liveKeys.get(refId);
      if (!keySchema) return controller.resolveLive(topic);

      const parsedKey = keySchema.parse(rawKey);
      return controller.resolveLive(encodeTopic(refId, parsedKey));
    },
    acquireLive(topic: string) {
      const { refId, rawKey } = splitTopic(topic);
      const keySchema = liveKeys.get(refId);
      if (!keySchema) return controller.acquireLive(topic);

      const parsedKey = keySchema.parse(rawKey);
      return controller.acquireLive(encodeTopic(refId, parsedKey));
    },
    async dispose() {
      await controller.dispose?.();
    },
  };

  function collectContractValidators(definitions: ContractDefinitions, prefix: string[]): void {
    for (const [name, def] of Object.entries(definitions)) {
      const fullPath = [...prefix, name].join('.');
      if (!isEndpointDef(def)) {
        collectContractValidators(def, [...prefix, name]);
        continue;
      }

      collectEndpointValidators(fullPath, def);
    }
  }

  function collectEndpointValidators(fullPath: string, def: EndpointDef): void {
    switch (def.kind) {
      case 'procedure':
        procedures.set(fullPath, {
          parseInput: (input) => def.input.parse(input),
          parseOutput: (output) => def.output.parse(output),
        });
        break;
      case 'downloadFile':
        procedures.set(fullPath, {
          parseInput: (input) => def.input.parse(input),
          parseOutput: (output) => parseDownloadFileOutput(def, output),
        });
        break;
      case 'uploadFile':
        procedures.set(fullPath, {
          parseInput: (input) => def.input.parse(input),
          parseOutput: (output) => resultSchema(def.result, def.error).parse(output),
        });
        break;
      case 'liveLog':
      case 'eventStream':
        liveKeys.set(def.id, def.keySchema);
        break;
      case 'liveJob':
        procedures.set(`${fullPath}.start`, {
          parseInput: (input) => def.input.parse(input),
          parseOutput: (output) => jobStartOutputSchema.parse(output),
        });
        procedures.set(`${fullPath}.cancel`, {
          parseInput: (input) => jobKeySchema.parse(input),
        });
        liveKeys.set(def.id, jobKeySchema);
        break;
      case 'liveModel':
        collectLiveModelValidators(fullPath, def);
        break;
    }
  }

  function collectLiveModelValidators(fullPath: string, def: LiveModelDef): void {
    for (const state of Object.values(def.states)) {
      liveKeys.set(state.id, def.keySchema);
    }

    for (const [mutationName, mutationDef] of Object.entries(def.mutations)) {
      const outputSchema = liveModelMutationOutputSchema(mutationDef);
      procedures.set(`${fullPath}.${mutationName}`, {
        parseInput: (input) => parseLiveModelMutationInput(def, mutationDef, input),
        parseOutput: (output) => outputSchema.parse(output),
      });
    }
  }
}

function parseDownloadFileOutput(def: DownloadFileEndpointDef, output: unknown): unknown {
  if (isDownloadFileOpenResult(output)) {
    return {
      success: true,
      data: markDownloadFileOpen(
        def.meta.parse(output.data.meta) as WireFileMeta,
        output.data.source
      ),
    };
  }

  if (isRecord(output) && output.success === false) {
    return { success: false, error: def.error.parse(output.error) };
  }

  return z.never().parse(output);
}

function parseLiveModelMutationInput(
  group: LiveModelDef,
  def: MutationDef,
  input: unknown
): { key: unknown; input: Record<string, unknown>; mutationId?: string } {
  const envelope = input as { key?: unknown; input?: unknown; mutationId?: unknown };
  const mutationInput = parseMutationInput(def.input, envelope.input);
  return {
    key: group.keySchema.parse(envelope.key),
    input: (mutationInput ?? {}) as Record<string, unknown>,
    mutationId: typeof envelope.mutationId === 'string' ? envelope.mutationId : undefined,
  };
}

function parseMutationInput(schema: z.ZodTypeAny, input: unknown): unknown {
  const parsed = schema.safeParse(input);
  if (parsed.success) return parsed.data;
  if (isEmptyRecord(input) && schema.safeParse(undefined).success) {
    return schema.parse(undefined);
  }
  return schema.parse(input);
}

function liveModelMutationOutputSchema(def: MutationDef): z.ZodTypeAny {
  // JSON transports drop keys with `undefined` values, so when the mutation data schema accepts
  // `undefined` (e.g. z.void()), the `data` key must be allowed to be absent entirely.
  const dataSchema = def.data.safeParse(undefined).success ? def.data.optional() : def.data;
  return resultSchema(
    z.object({ data: dataSchema, cursors: z.array(liveCursorEntrySchema) }),
    def.error
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isEmptyRecord(value: unknown): value is Record<string, never> {
  return isRecord(value) && Object.keys(value).length === 0;
}
