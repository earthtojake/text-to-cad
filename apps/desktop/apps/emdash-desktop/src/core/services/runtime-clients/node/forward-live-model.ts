import { ok, type Result } from '@emdash/shared';
import type { LiveModelMutationEnvelope, LiveModelProvider } from '@emdash/wire/rpc';
import type {
  LiveModelClientHandle,
  LiveModelDef,
  LiveModelKey,
  LiveModelMutations,
  LiveMutationResult,
  MutationData,
  MutationError,
  MutationInput,
} from '@emdash/wire/rpc';

/**
 * Forwards a live-model contract to an upstream runtime's model, resolving the upstream
 * live source per key (host/workspace lookup happens inside `resolveState`, typically via
 * a contract client's `.state(key, name).asLiveSource()`).
 *
 * This is contract forwarding over the client-handle channel, not state authoring: no
 * state is owned here, and upstream snapshots and updates pass through untouched. The
 * `cell` + `expose` authoring mandate (wire-architecture state-system endgame) covers
 * hand-authored state models only — do not copy this shape to author one.
 */
export function forwardLiveModel<Group extends LiveModelDef>(
  contract: Group,
  resolveState: LiveModelProvider<Group>['resolveState'],
  options: { readonly mutationMessage?: string } = {}
): LiveModelProvider<Group> {
  return {
    kind: 'liveModelProvider',
    contract,
    resolveState,
    async runMutation() {
      throw new Error(options.mutationMessage ?? `Live model '${contract.id}' has no mutations`);
    },
  };
}

type MutationInputsOf<Model extends LiveModelDef> = {
  [Name in keyof LiveModelMutations<Model>]: MutationInput<LiveModelMutations<Model>[Name]>;
};

type MutationResultsOf<Model extends LiveModelDef> = {
  [Name in keyof LiveModelMutations<Model>]: Result<
    MutationData<LiveModelMutations<Model>[Name]>,
    MutationError<LiveModelMutations<Model>[Name]>
  >;
};

type LocalMutationNames<
  Local extends LiveModelDef,
  Upstream extends LiveModelDef,
> = keyof LiveModelMutations<Local> & keyof LiveModelMutations<Upstream>;

/**
 * Compile-time witness that every local mutation can run against the upstream model:
 * the local mutation names are a subset of the upstream's, with identical input shapes,
 * and upstream results at most as wide as the local ones (desktop contracts widen
 * upstream errors with runtime-resolve errors). Resolves to an empty tuple when
 * compatible; an incompatible forward demands an impossible extra argument and fails at
 * the call site.
 */
type ForwardableWitness<Local extends LiveModelDef, Upstream extends LiveModelDef> = [
  keyof LiveModelMutations<Local>,
] extends [keyof LiveModelMutations<Upstream>]
  ? MutationInputsOf<Local> extends Pick<
      MutationInputsOf<Upstream>,
      LocalMutationNames<Local, Upstream>
    >
    ? Pick<
        MutationResultsOf<Upstream>,
        LocalMutationNames<Local, Upstream>
      > extends MutationResultsOf<Local>
      ? []
      : [incompatibleMutationResults: never]
    : [incompatibleMutationInputs: never]
  : [missingUpstreamMutations: never];

/**
 * Forwards one live-model mutation envelope to an upstream model client handle,
 * remapping the local key onto the upstream key shape and rebinding the returned
 * mutation cursors onto the local model's state ids and key.
 *
 * Once the mutation name is generic, TypeScript cannot relate the per-name input and
 * result types across two contract types even when they are compatible for every
 * instantiation; `ForwardableWitness` proves that compatibility at the (concrete) call
 * site, and the casts below are the one localized bridge over the deferred generics.
 */
export async function forwardModelMutation<
  Upstream extends LiveModelDef,
  Local extends LiveModelDef,
  Name extends Extract<keyof LiveModelMutations<Local>, string>,
>(
  upstream: LiveModelClientHandle<Upstream>,
  local: Local,
  name: Name,
  envelope: LiveModelMutationEnvelope<Local, Name>,
  upstreamKey: LiveModelKey<NoInfer<Upstream>>,
  ..._witness: ForwardableWitness<NoInfer<Local>, NoInfer<Upstream>>
): Promise<
  LiveMutationResult<
    MutationData<LiveModelMutations<Local>[Name]>,
    MutationError<LiveModelMutations<Local>[Name]>
  >
> {
  const result = (await upstream.mutate(
    name as never,
    {
      key: upstreamKey,
      input: envelope.input,
      mutationId: envelope.mutationId,
    } as never
  )) as LiveMutationResult<
    MutationData<LiveModelMutations<Local>[Name]>,
    MutationError<LiveModelMutations<Local>[Name]>
  >;
  if (!result.success) return result;
  const localStateIds = new Map(
    Object.entries(upstream.def.states).flatMap(([stateName, state]) => {
      const localState = local.states[stateName];
      return localState ? [[state.id, localState.id] as const] : [];
    })
  );
  return ok({
    ...result.data,
    cursors: result.data.cursors.map((cursor) => ({
      ...cursor,
      model: localStateIds.get(cursor.model) ?? cursor.model,
      key: envelope.key,
    })),
  });
}
