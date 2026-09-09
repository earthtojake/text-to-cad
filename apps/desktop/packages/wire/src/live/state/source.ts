import { createEmitter, type Unsubscribe } from '@emdash/shared';
import type { LiveCursor, LiveSnapshot, LiveUpdate } from '../../api/channel';
import { type Patch, produceWithPatches } from './immer-setup';

export type LiveStateSourceProduceOptions = {
  mutationIds?: string[];
};

/**
 * Transport-agnostic live model.
 *
 * Holds authoritative state, emits structural Immer patches on each mutation,
 * and fans out LiveUpdate events to subscribers. One instance per logical
 * session/resource.
 *
 * Invariant: `current` is only ever *replaced* by a new reference (via
 * `produce()` and `reseed()`), never mutated in place. `snapshot()` clones on
 * the way out so the public API never leaks a live internal reference.
 *
 * Keep the state T as plain JSON (no Date/Map/Set/class instances). Patches
 * travel as opaque unknown across the wire; non-JSON values in the patched
 * result cause validation failures and resync loops on the client.
 */
export class LiveStateSource<T> {
  private readonly emitter = createEmitter<LiveUpdate>();
  private generation: number;
  private sequence = 0;

  constructor(
    private current: T,
    generation = Date.now()
  ) {
    this.generation = generation;
  }

  get cursor(): LiveCursor {
    return {
      generation: this.generation,
      sequence: this.sequence,
    };
  }

  /**
   * Returns a deep-cloned snapshot of the current state.
   * Use this to respond to the `snapshot` contract endpoint.
   */
  snapshot(): LiveSnapshot<T> {
    return {
      generation: this.generation,
      sequence: this.sequence,
      timestamp: Date.now(),
      data: structuredClone(this.current),
    };
  }

  /**
   * Mutates state via a synchronous mutator applied to an Immer draft.
   * Uses structural sharing — only objects along mutated paths are copied.
   * Emits a patch delta only when the mutation produces an effective change.
   *
   * Returns the model cursor that contains the mutation. For no-ops, this is
   * the current cursor because the authoritative state already reflected the
   * requested operation.
   */
  produce(mutator: (draft: T) => void, options: LiveStateSourceProduceOptions = {}): LiveCursor {
    const [next, patches] = produceWithPatches(
      this.current,
      mutator as (draft: object) => void
    ) as [T, Patch[], Patch[]];
    if (patches.length === 0) return this.cursor; // no-op suppression
    this.current = next; // structurally shared reference swap
    const baseSequence = this.sequence;
    this.sequence += 1;
    this.emitter.emit({
      generation: this.generation,
      baseSequence,
      sequence: this.sequence,
      timestamp: Date.now(),
      delta: patches,
      mutationIds: options.mutationIds,
    });
    return this.cursor;
  }

  /** Replaces the complete value while retaining normal patch and no-op semantics. */
  replace(next: T, options: LiveStateSourceProduceOptions = {}): LiveCursor {
    const [value, patches] = produceWithPatches(this.current, () => next) as [T, Patch[], Patch[]];
    if (patches.length === 0) return this.cursor;
    this.current = value;
    const baseSequence = this.sequence;
    this.sequence += 1;
    this.emitter.emit({
      generation: this.generation,
      baseSequence,
      sequence: this.sequence,
      timestamp: Date.now(),
      delta: patches,
      mutationIds: options.mutationIds,
    });
    return this.cursor;
  }

  /**
   * Resets the generation (and optionally the state) to force all connected
   * clients to resync from scratch. Sequence resets to 0. Does NOT emit —
   * clients learn of the new generation on the next delta or when they next
   * call snapshot().
   */
  reseed(next?: T): void {
    if (next !== undefined) this.current = next;
    this.generation = Date.now();
    this.sequence = 0;
  }

  subscribe(cb: (update: LiveUpdate) => void): Unsubscribe {
    return this.emitter.subscribe(cb);
  }

  dispose(): void {
    this.emitter.clear();
  }
}
