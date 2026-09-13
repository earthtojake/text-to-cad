import { resultSchema, type Result } from '@emdash/shared';
import { z } from 'zod';
import type { LiveMutationInput, Mutator } from './channel';
import type { WireFileMeta } from './protocol';

export const contractSymbol: unique symbol = Symbol('wire.contract');

export type ProcedureDef<
  InputSchema extends z.ZodTypeAny = z.ZodTypeAny,
  OutputSchema extends z.ZodTypeAny = z.ZodTypeAny,
> = {
  kind: 'procedure';
  input: InputSchema;
  output: OutputSchema;
};

export type LiveStateDef<
  Id extends string = string,
  KeySchema extends z.ZodTypeAny = z.ZodTypeAny,
  DataSchema extends z.ZodTypeAny = z.ZodTypeAny,
> = {
  kind: 'liveState';
  id: Id;
  keySchema: KeySchema;
  dataSchema: DataSchema;
};

export type LiveLogEndpointDef<
  Id extends string = string,
  KeySchema extends z.ZodTypeAny = z.ZodTypeAny,
> = {
  kind: 'liveLog';
  id: Id;
  keySchema: KeySchema;
};

export type EventStreamEndpointDef<
  Id extends string = string,
  KeySchema extends z.ZodTypeAny = z.ZodTypeAny,
  EventSchema extends z.ZodTypeAny = z.ZodTypeAny,
  Resourced extends boolean = boolean,
> = {
  kind: 'eventStream';
  id: Id;
  keySchema: KeySchema;
  eventSchema: EventSchema;
} & (Resourced extends true ? { resourced: true } : { resourced?: false });

export type LiveJobEndpointDef<
  Id extends string = string,
  InputSchema extends z.ZodTypeAny = z.ZodTypeAny,
  ProgressSchema extends z.ZodTypeAny = z.ZodTypeAny,
  ResultSchema extends z.ZodTypeAny = z.ZodTypeAny,
  ErrorSchema extends z.ZodTypeAny = z.ZodTypeAny,
> = {
  kind: 'liveJob';
  id: Id;
  input: InputSchema;
  progress: ProgressSchema;
  result: ResultSchema;
  error: ErrorSchema;
};

export const wireFileMetaSchema = z.object({
  name: z.string(),
  mimeType: z.string(),
  size: z.number().nonnegative().optional(),
  lastModified: z.number().optional(),
});

export type DownloadFileEndpointDef<
  Id extends string = string,
  InputSchema extends z.ZodTypeAny = z.ZodTypeAny,
  MetaSchema extends z.ZodTypeAny = z.ZodTypeAny,
  ErrorSchema extends z.ZodTypeAny = z.ZodTypeAny,
> = {
  kind: 'downloadFile';
  id: Id;
  input: InputSchema;
  meta: MetaSchema;
  error: ErrorSchema;
};

export type UploadFileEndpointDef<
  Id extends string = string,
  InputSchema extends z.ZodTypeAny = z.ZodTypeAny,
  ResultSchema extends z.ZodTypeAny = z.ZodTypeAny,
  ErrorSchema extends z.ZodTypeAny = z.ZodTypeAny,
> = {
  kind: 'uploadFile';
  id: Id;
  input: InputSchema;
  accept?: readonly string[];
  maxSize?: number;
  result: ResultSchema;
  error: ErrorSchema;
};

export type MutationDef<
  InputSchema extends z.ZodTypeAny = z.ZodTypeAny,
  DataSchema extends z.ZodTypeAny = z.ZodTypeAny,
  ErrorSchema extends z.ZodTypeAny = z.ZodTypeAny,
> = {
  kind: 'mutation';
  input: InputSchema;
  data: DataSchema;
  error: ErrorSchema;
  handler?: LiveModelMutationHandler<InputSchema, DataSchema, ErrorSchema>;
};

export type LiveModelMutationHandler<
  InputSchema extends z.ZodTypeAny,
  DataSchema extends z.ZodTypeAny,
  ErrorSchema extends z.ZodTypeAny,
> = {
  bivarianceHack(
    ctx: LiveModelMutationCtx<LiveModelDef>,
    input: LiveMutationInput<z.infer<InputSchema>>
  ):
    | Promise<Result<z.infer<DataSchema>, z.infer<ErrorSchema>>>
    | Result<z.infer<DataSchema>, z.infer<ErrorSchema>>;
}['bivarianceHack'];

export type LiveModelDef<
  KeySchema extends z.ZodTypeAny = z.ZodTypeAny,
  States extends Record<string, LiveStateDef> = Record<string, LiveStateDef>,
  Mutations extends Record<string, MutationDef> = Record<string, MutationDef>,
> = {
  kind: 'liveModel';
  id: string;
  keySchema: KeySchema;
  states: States;
  mutations: Mutations;
};

export type EndpointDef =
  | ProcedureDef
  | LiveLogEndpointDef
  | EventStreamEndpointDef
  | LiveJobEndpointDef
  | LiveModelDef
  | DownloadFileEndpointDef
  | UploadFileEndpointDef;

export type ContractEntry = EndpointDef | Contract<ContractDefinitions>;
export interface ContractDefinitions {
  [key: string]: ContractEntry;
}
export type Contract<Defs extends ContractDefinitions> = Defs & {
  readonly [contractSymbol]: true;
};

export type EndpointInput<Def> =
  Def extends ProcedureDef<infer Input, z.ZodTypeAny> ? z.infer<Input> : never;

export type EndpointOutput<Def> =
  Def extends ProcedureDef<z.ZodTypeAny, infer Output> ? z.infer<Output> : never;

export type MutationInput<Def> =
  Def extends MutationDef<infer Input, z.ZodTypeAny, z.ZodTypeAny> ? z.infer<Input> : never;

export type MutationData<Def> =
  Def extends MutationDef<z.ZodTypeAny, infer Data, z.ZodTypeAny> ? z.infer<Data> : never;

export type MutationError<Def> =
  Def extends MutationDef<z.ZodTypeAny, z.ZodTypeAny, infer Error> ? z.infer<Error> : never;

export type LiveStateKey<Def> =
  Def extends LiveStateDef<string, infer Key, z.ZodTypeAny> ? z.infer<Key> : never;

export type LiveStateData<Def> =
  Def extends LiveStateDef<string, z.ZodTypeAny, infer Data> ? z.infer<Data> : never;

export type LiveLogKey<Def> =
  Def extends LiveLogEndpointDef<string, infer Key> ? z.infer<Key> : never;

export type EventStreamKey<Def> =
  Def extends EventStreamEndpointDef<string, infer Key, z.ZodTypeAny> ? z.infer<Key> : never;

export type EventStreamEvent<Def> =
  Def extends EventStreamEndpointDef<string, z.ZodTypeAny, infer Event> ? z.infer<Event> : never;

export type JobInput<Def> =
  Def extends LiveJobEndpointDef<string, infer Input, z.ZodTypeAny, z.ZodTypeAny, z.ZodTypeAny>
    ? z.infer<Input>
    : never;

export type JobProgress<Def> =
  Def extends LiveJobEndpointDef<string, z.ZodTypeAny, infer Progress, z.ZodTypeAny, z.ZodTypeAny>
    ? z.infer<Progress>
    : never;

export type JobResult<Def> =
  Def extends LiveJobEndpointDef<string, z.ZodTypeAny, z.ZodTypeAny, infer Result, z.ZodTypeAny>
    ? z.infer<Result>
    : never;

export type JobError<Def> =
  Def extends LiveJobEndpointDef<string, z.ZodTypeAny, z.ZodTypeAny, z.ZodTypeAny, infer Error>
    ? z.infer<Error>
    : never;

export type DownloadFileInput<Def> =
  Def extends DownloadFileEndpointDef<string, infer Input, z.ZodTypeAny, z.ZodTypeAny>
    ? z.infer<Input>
    : never;

export type DownloadFileMeta<Def> =
  Def extends DownloadFileEndpointDef<string, z.ZodTypeAny, infer Meta, z.ZodTypeAny>
    ? z.infer<Meta> & WireFileMeta
    : never;

export type DownloadFileError<Def> =
  Def extends DownloadFileEndpointDef<string, z.ZodTypeAny, z.ZodTypeAny, infer Error>
    ? z.infer<Error>
    : never;

export type UploadFileInput<Def> =
  Def extends UploadFileEndpointDef<string, infer Input, z.ZodTypeAny, z.ZodTypeAny>
    ? z.infer<Input>
    : never;

export type UploadFileResult<Def> =
  Def extends UploadFileEndpointDef<string, z.ZodTypeAny, infer Result, z.ZodTypeAny>
    ? z.infer<Result>
    : never;

export type UploadFileError<Def> =
  Def extends UploadFileEndpointDef<string, z.ZodTypeAny, z.ZodTypeAny, infer Error>
    ? z.infer<Error>
    : never;

export type LiveModelKey<Def> =
  Def extends LiveModelDef<infer Key, Record<string, LiveStateDef>, Record<string, MutationDef>>
    ? z.infer<Key>
    : never;

export type LiveModelStates<Def> =
  Def extends LiveModelDef<z.ZodTypeAny, infer Models, Record<string, MutationDef>>
    ? Models
    : never;

export type LiveModelMutations<Def> =
  Def extends LiveModelDef<z.ZodTypeAny, Record<string, LiveStateDef>, infer Mutations>
    ? Mutations
    : never;

export interface LiveModelMutationCtx<Group extends LiveModelDef = LiveModelDef> {
  readonly mutationId: string;
  readonly key: LiveModelKey<Group>;
  produce<Name extends keyof LiveModelStates<Group>>(
    name: Name,
    mutator: Mutator<LiveStateData<LiveModelStates<Group>[Name]>>
  ): void;
}

export function procedure<
  InputSchema extends z.ZodTypeAny,
  OutputSchema extends z.ZodTypeAny,
>(def: { input: InputSchema; output: OutputSchema }): ProcedureDef<InputSchema, OutputSchema> {
  return { kind: 'procedure', ...def };
}

export function fallible<InputSchema extends z.ZodTypeAny, ErrorSchema extends z.ZodTypeAny>(def: {
  input: InputSchema;
  error: ErrorSchema;
}): ProcedureDef<InputSchema, z.ZodType<Result<void, z.output<ErrorSchema>>>>;
export function fallible<
  InputSchema extends z.ZodTypeAny,
  DataSchema extends z.ZodTypeAny,
  ErrorSchema extends z.ZodTypeAny,
>(def: {
  input: InputSchema;
  data: DataSchema;
  error: ErrorSchema;
}): ProcedureDef<InputSchema, ReturnType<typeof resultSchema<DataSchema, ErrorSchema>>>;
export function fallible(def: {
  input: z.ZodTypeAny;
  data?: z.ZodTypeAny;
  error: z.ZodTypeAny;
}): ProcedureDef {
  // JSON transports omit properties whose value is undefined. When the data schema accepts
  // undefined (including the no-data case), the success envelope accepts an absent data property
  // at the wire boundary and normalizes it back to the in-memory Result shape.
  const data = def.data ?? z.void();
  const output = data.safeParse(undefined).success
    ? resultSchema(data.optional(), def.error).transform((result) =>
        result.success ? { success: true as const, data: result.data } : result
      )
    : resultSchema(data, def.error);
  return procedure({
    input: def.input,
    output,
  });
}

export function liveLog<KeySchema extends z.ZodTypeAny>(def: {
  key: KeySchema;
}): LiveLogEndpointDef<string, KeySchema> {
  return { kind: 'liveLog', id: '', keySchema: def.key };
}

export function eventStream<KeySchema extends z.ZodTypeAny, EventSchema extends z.ZodTypeAny>(def: {
  key: KeySchema;
  event: EventSchema;
}): EventStreamEndpointDef<string, KeySchema, EventSchema, false> {
  return { kind: 'eventStream', id: '', keySchema: def.key, eventSchema: def.event };
}

export function resourcedStream<
  KeySchema extends z.ZodTypeAny,
  EventSchema extends z.ZodTypeAny,
>(def: {
  key: KeySchema;
  event: EventSchema;
}): EventStreamEndpointDef<string, KeySchema, EventSchema, true> {
  return {
    kind: 'eventStream',
    id: '',
    keySchema: def.key,
    eventSchema: def.event,
    resourced: true,
  };
}

export function liveJob<
  InputSchema extends z.ZodTypeAny,
  ProgressSchema extends z.ZodTypeAny,
  ResultSchema extends z.ZodTypeAny,
  ErrorSchema extends z.ZodTypeAny,
>(def: {
  input: InputSchema;
  progress: ProgressSchema;
  result: ResultSchema;
  error: ErrorSchema;
}): LiveJobEndpointDef<string, InputSchema, ProgressSchema, ResultSchema, ErrorSchema> {
  return { kind: 'liveJob', id: '', ...def };
}

export function downloadFile<
  InputSchema extends z.ZodTypeAny,
  MetaSchema extends z.ZodTypeAny = typeof wireFileMetaSchema,
  ErrorSchema extends z.ZodTypeAny = z.ZodUnknown,
>(def: {
  input: InputSchema;
  meta?: MetaSchema;
  error: ErrorSchema;
}): DownloadFileEndpointDef<string, InputSchema, MetaSchema, ErrorSchema> {
  return {
    kind: 'downloadFile',
    id: '',
    input: def.input,
    meta: (def.meta ?? wireFileMetaSchema) as MetaSchema,
    error: def.error,
  };
}

export function uploadFile<
  InputSchema extends z.ZodTypeAny,
  ResultSchema extends z.ZodTypeAny,
  ErrorSchema extends z.ZodTypeAny,
>(def: {
  input: InputSchema;
  accept?: readonly string[];
  maxSize?: number;
  result: ResultSchema;
  error: ErrorSchema;
}): UploadFileEndpointDef<string, InputSchema, ResultSchema, ErrorSchema> {
  return { kind: 'uploadFile', id: '', ...def };
}

/**
 * Defines a live model contract member mutation. Handlers should be pure functions
 * of the member drafts and input. The optimistic group utility may run the same
 * handler client-side to derive previews before the server confirms them.
 */
export function mutation<
  InputSchema extends z.ZodTypeAny,
  DataSchema extends z.ZodTypeAny,
  ErrorSchema extends z.ZodTypeAny,
>(
  def: { input: InputSchema; data: DataSchema; error: ErrorSchema },
  handler: LiveModelMutationHandler<InputSchema, DataSchema, ErrorSchema>
): MutationDef<InputSchema, DataSchema, ErrorSchema>;
export function mutation<
  InputSchema extends z.ZodTypeAny,
  DataSchema extends z.ZodTypeAny,
  ErrorSchema extends z.ZodTypeAny,
>(def: {
  input: InputSchema;
  data: DataSchema;
  error: ErrorSchema;
}): MutationDef<InputSchema, DataSchema, ErrorSchema>;
export function mutation(
  def: { input: z.ZodTypeAny; data: z.ZodTypeAny; error: z.ZodTypeAny },
  handler?: LiveModelMutationHandler<z.ZodTypeAny, z.ZodTypeAny, z.ZodTypeAny>
): MutationDef {
  return { kind: 'mutation', ...def, handler };
}

export function liveState<DataSchema extends z.ZodTypeAny>(def: {
  data: DataSchema;
}): LiveStateDef<string, z.ZodUnknown, DataSchema> {
  return {
    kind: 'liveState',
    id: '',
    keySchema: z.unknown(),
    dataSchema: def.data,
  };
}

export function liveModel<
  KeySchema extends z.ZodTypeAny,
  States extends Record<string, LiveStateDef>,
  Mutations extends Record<string, MutationDef> = {},
>(def: {
  key: KeySchema;
  states: States;
  mutations?: Mutations;
}): LiveModelDef<
  KeySchema,
  {
    [Name in keyof States]: LiveStateDef<string, KeySchema, States[Name]['dataSchema']>;
  },
  Mutations
> {
  const states: Record<string, LiveStateDef> = {};
  for (const [name, state] of Object.entries(def.states)) {
    states[name] = {
      ...state,
      kind: 'liveState',
      id: '',
      keySchema: def.key,
    };
  }
  return {
    kind: 'liveModel',
    id: '',
    keySchema: def.key,
    states: states as {
      [Name in keyof States]: LiveStateDef<string, KeySchema, States[Name]['dataSchema']>;
    },
    mutations: (def.mutations ?? {}) as Mutations,
  };
}

export function defineContract<const Defs extends ContractDefinitions>(
  definitions: Defs
): Contract<Defs> {
  return finalizeContract(definitions, []) as Contract<Defs>;
}

function finalizeContract(
  definitions: ContractDefinitions,
  prefix: string[]
): Contract<ContractDefinitions> {
  const finalized: ContractDefinitions = {};
  for (const [name, def] of Object.entries(definitions)) {
    if (isMutationDef(def)) {
      throw new Error(
        `Mutation '${[...prefix, name].join('.')}' must be declared inside liveModel().mutations`
      );
    }
    finalized[name] = isEndpointDef(def)
      ? finalizeEndpoint([...prefix, name], def)
      : finalizeContract(def, [...prefix, name]);
  }
  Object.defineProperty(finalized, contractSymbol, {
    value: true,
    enumerable: false,
  });
  return finalized as Contract<ContractDefinitions>;
}

function finalizeEndpoint(path: string[], def: EndpointDef): EndpointDef {
  const id = path.join('.');
  switch (def.kind) {
    case 'liveLog':
      return { ...def, id };
    case 'eventStream':
      return { ...def, id };
    case 'liveJob':
      return { ...def, id };
    case 'downloadFile':
      return { ...def, id };
    case 'uploadFile':
      return { ...def, id };
    case 'liveModel':
      return finalizeLiveModelEndpoint(id, def);
    case 'procedure':
      return { ...def };
  }
}

function finalizeLiveModelEndpoint(id: string, def: LiveModelDef): LiveModelDef {
  const states: Record<string, LiveStateDef> = {};
  for (const [stateName, state] of Object.entries(def.states)) {
    states[stateName] = {
      ...state,
      id: `${id}.${stateName}`,
      keySchema: def.keySchema,
    };
  }
  const mutations: Record<string, MutationDef> = {};
  for (const [mutationName, memberMutation] of Object.entries(def.mutations)) {
    mutations[mutationName] = { ...memberMutation };
  }
  return {
    ...def,
    id,
    states,
    mutations,
  };
}

function isMutationDef(value: unknown): value is MutationDef {
  return (
    typeof value === 'object' && value !== null && (value as { kind?: unknown }).kind === 'mutation'
  );
}

export function isEndpointDef(value: ContractEntry): value is EndpointDef {
  if (typeof value !== 'object' || value === null) return false;
  const kind = (value as { kind?: unknown }).kind;
  switch (kind) {
    case 'liveLog':
    case 'eventStream':
    case 'liveJob':
    case 'liveModel':
    case 'downloadFile':
    case 'uploadFile':
    case 'procedure':
      return true;
    default:
      return false;
  }
}
