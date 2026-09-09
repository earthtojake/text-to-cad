// Public `@emdash/wire/state` entry: the state kernel (cells, families,
// queries, optimistic views, pinning, observation) plus the wire bridge
// (`expose` on the serving side, `remote` on the consuming side).
export { assignDraft } from './bridge/assign-draft';
export {
  expose,
  type ExposedMutationContext,
  type ExposedMutationHandlers,
  type ExposedPublishMode,
  type ExposedPublishOptions,
  type ExposedStateResolver,
  type ExposedStates,
  type ExposeOptions,
} from './bridge/expose';
export { mapMutationErrors, type MutationErrorMapper } from './bridge/mutation-error';
export { publishStructural } from './bridge/publish-structural';
export {
  remote,
  type RemoteMember,
  type RemoteModel,
  type RemoteOptions,
  type RemoteState,
} from './bridge/remote';
export { cell, type Cell, type CellOptions } from './core/cell';
export { derived, type DerivedOptions } from './core/derived';
export { family, type Family, type FamilyOptions } from './core/family';
export {
  peek,
  revisionOf,
  snapshot,
  type CommitOptions,
  type Observer,
  type Readable,
  type Revision,
  type Snapshot,
  type StateStatus,
} from './core/node';
export { observe, type ObserveOptions } from './core/observe';
export { batch, flushStateTurn, type BatchMeta } from './core/scheduler';
export { whenReady } from './core/when-ready';
export { produce } from './live-immer';
export {
  optimistic,
  type ContractMutationInvocation,
  type OptimisticOptions,
  type OptimisticView,
  type PendingHandle,
} from './optimistic';
export { pin, prefetch, type PinSet } from './pin';
export { pokeChannel, type PokeChannel, type PokeSubscription } from './poke';
export { query, type Query, type QueryLane, type QueryOptions } from './query';
