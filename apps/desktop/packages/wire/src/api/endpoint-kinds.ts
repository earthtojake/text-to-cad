import type { PendingLease } from '@emdash/shared';
import type { LiveSource } from './channel';
import type { Connection } from './connect';
import type { CallMeta } from './controller';
import type {
  EventStreamEndpointDef,
  LiveJobEndpointDef,
  LiveLogEndpointDef,
  LiveModelDef,
} from './define';

/**
 * Internal seam between the RPC core and the live endpoint kinds.
 *
 * The core owns everything already generic on the wire — protocol messages,
 * topics, call/mutation dispatch, cancel, blobs, and the subscription-channel
 * lifecycle — and consumes the live kinds only through this interface. The
 * single implementation lives in `../live/endpoint-kinds.ts`; the dependency
 * is one-directional (rpc core ← live-kinds glue). This is deliberately not a
 * public extension API: no second endpoint-kind family exists, so the seam
 * stays internal until one does.
 */

export type LiveEndpointDef =
  | LiveLogEndpointDef
  | EventStreamEndpointDef
  | LiveJobEndpointDef
  | LiveModelDef;

export type MaybeAsyncLiveSource =
  | LiveSource
  | Promise<LiveSource | null | undefined>
  | null
  | undefined;

/** One live topic contributed by an endpoint: either resolvable or leasable. */
export type LiveTopicBinding = {
  id: string;
  resolve?(key: unknown): MaybeAsyncLiveSource;
  acquire?(key: unknown): PendingLease<LiveSource>;
};

export type LiveProcedureBinding = {
  path: string;
  handler(input: unknown, meta: CallMeta): Promise<unknown>;
};

export type LiveEndpointBinding = {
  topics: LiveTopicBinding[];
  procedures?: LiveProcedureBinding[];
  dispose?(): Promise<void>;
};

export type LiveEndpointKinds = {
  /** Controller side: resolves an endpoint implementation into topics and procedures. */
  bindEndpoint(def: LiveEndpointDef, impl: unknown, path: string): LiveEndpointBinding;
  /** Client side: constructs the typed handle object for an endpoint. */
  createEndpointClient(def: LiveEndpointDef, path: string, connection: Connection): unknown;
};
