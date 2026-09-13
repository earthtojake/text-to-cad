import { createEmitter, type Unsubscribe } from '@emdash/shared';
import { stableStringify } from '@emdash/shared/util';
import type { EventStreamSnapshotData, LiveSnapshot, LiveUpdate } from '../../api/channel';
import type { EventStreamEndpointDef, EventStreamEvent, EventStreamKey } from '../../api/define';
import type { EventStreamDelta } from '../protocol';

export type EventStreamSourceOptions = {
  generation?: number;
  onFirst?: () => void;
  onEmpty?: () => void;
  activate?: () => Promise<Unsubscribe>;
};

type EventStreamSourceSubscribeResult<Resourced extends boolean> = Resourced extends true
  ? Promise<Unsubscribe>
  : Unsubscribe;

type IsResourcedEventStream<Def extends EventStreamEndpointDef> = Def extends {
  resourced: true;
}
  ? true
  : false;

/**
 * A no-retention event stream. Events emitted while no subscriber is attached are dropped.
 */
export class EventStreamSource<Event = unknown, Resourced extends boolean = false> {
  private readonly emitter = createEmitter<LiveUpdate>();
  private readonly onFirst: (() => void) | undefined;
  private readonly onEmpty: (() => void) | undefined;
  private readonly activate: (() => Promise<Unsubscribe>) | undefined;
  private readonly generation: number;
  private activation: Promise<void> | undefined;
  private activationDisposer: Unsubscribe | undefined;
  private sequence = 0;
  private disposed = false;

  constructor(options: EventStreamSourceOptions = {}) {
    this.generation = options.generation ?? Date.now();
    this.onFirst = options.onFirst;
    this.onEmpty = options.onEmpty;
    this.activate = options.activate;
  }

  get subscriberCount(): number {
    return this.emitter.size;
  }

  emit(event: Event): void {
    if (this.emitter.size === 0) return;

    const baseSequence = this.sequence;
    this.sequence += 1;
    const delta: EventStreamDelta = { event };
    this.emitter.emit({
      generation: this.generation,
      baseSequence,
      sequence: this.sequence,
      timestamp: Date.now(),
      delta,
    });
  }

  snapshot(): LiveSnapshot<EventStreamSnapshotData> {
    return {
      generation: this.generation,
      sequence: this.sequence,
      timestamp: Date.now(),
      data: {},
    };
  }

  subscribe(cb: (update: LiveUpdate) => void): EventStreamSourceSubscribeResult<Resourced> {
    if (this.disposed) throw new Error('EventStreamSource is disposed');
    const wasEmpty = this.emitter.size === 0;
    const detach = this.emitter.subscribe(cb);
    let active = true;
    const unsubscribe = (): void => {
      if (!active) return;
      active = false;
      detach();
      if (this.emitter.size !== 0) return;
      this.disposeActivation();
      this.onEmpty?.();
    };

    if (!this.activate) {
      if (wasEmpty && this.emitter.size > 0) this.onFirst?.();
      return unsubscribe as EventStreamSourceSubscribeResult<Resourced>;
    }

    const activation = this.activation ?? this.startActivation();
    return activation.then(
      () => unsubscribe,
      (error: unknown) => {
        unsubscribe();
        throw error;
      }
    ) as EventStreamSourceSubscribeResult<Resourced>;
  }

  dispose(): void {
    if (this.disposed) return;
    this.disposed = true;
    this.emitter.clear();
    this.disposeActivation();
  }

  private startActivation(): Promise<void> {
    const activation = Promise.resolve()
      .then(() => this.activate!())
      .then((disposer) => {
        if (this.activation !== activation) {
          disposer();
          return;
        }
        this.activationDisposer = disposer;
        if (this.disposed || this.emitter.size === 0) this.disposeActivation();
      });
    this.activation = activation;
    void activation.catch(() => {
      if (this.activation !== activation) return;
      this.activation = undefined;
      this.activationDisposer = undefined;
    });
    return activation;
  }

  private disposeActivation(): void {
    const disposer = this.activationDisposer;
    if (!disposer) return;
    this.activationDisposer = undefined;
    this.activation = undefined;
    disposer();
  }
}

export type EventStreamHost<Def extends EventStreamEndpointDef = EventStreamEndpointDef> = {
  readonly kind: 'eventStreamHost';
  readonly def: Def;
  emit(key: EventStreamKey<Def>, event: EventStreamEvent<Def>): void;
  resolve(
    key: EventStreamKey<Def>
  ): EventStreamSource<EventStreamEvent<Def>, IsResourcedEventStream<Def>>;
  dispose(): void;
};

type PlainEventStreamHostOptions<Def extends EventStreamEndpointDef> = {
  onActive?: (key: EventStreamKey<Def>) => void;
  onIdle?: (key: EventStreamKey<Def>) => void;
};

type ResourcedEventStreamHostOptions<Def extends EventStreamEndpointDef> = {
  activate: (key: EventStreamKey<Def>) => Promise<Unsubscribe>;
};

export type EventStreamHostOptions<Def extends EventStreamEndpointDef = EventStreamEndpointDef> =
  Def extends { resourced: true }
    ? ResourcedEventStreamHostOptions<Def>
    : PlainEventStreamHostOptions<Def>;

export function createEventStreamHost<Def extends EventStreamEndpointDef>(
  def: Def,
  ...args: Def extends { resourced: true }
    ? [options: ResourcedEventStreamHostOptions<Def>]
    : [options?: PlainEventStreamHostOptions<Def>]
): EventStreamHost<Def> {
  const options = (args[0] ?? {}) as EventStreamHostOptions<Def>;
  const sources = new Map<
    string,
    EventStreamSource<EventStreamEvent<Def>, IsResourcedEventStream<Def>>
  >();

  function keyOf(key: EventStreamKey<Def>): string {
    return stableStringify(key);
  }

  function removeIfEmpty(
    key: EventStreamKey<Def>,
    keyId: string,
    source: EventStreamSource<EventStreamEvent<Def>, IsResourcedEventStream<Def>>
  ): void {
    if (source.subscriberCount === 0 && sources.get(keyId) === source) {
      sources.delete(keyId);
      if (!def.resourced) (options as PlainEventStreamHostOptions<Def>).onIdle?.(key);
    }
  }

  return {
    kind: 'eventStreamHost',
    def,
    emit(key, event) {
      sources.get(keyOf(key))?.emit(event);
    },
    resolve(key) {
      const keyId = keyOf(key);
      let source = sources.get(keyId);
      if (!source) {
        const sourceKey = key;
        const created = new EventStreamSource<EventStreamEvent<Def>, IsResourcedEventStream<Def>>({
          activate: def.resourced
            ? () => (options as ResourcedEventStreamHostOptions<Def>).activate(sourceKey)
            : undefined,
          onFirst: () => (options as PlainEventStreamHostOptions<Def>).onActive?.(sourceKey),
          onEmpty: () => removeIfEmpty(sourceKey, keyId, created),
        });
        source = created;
        sources.set(keyId, created);
      }
      return source;
    },
    dispose() {
      for (const source of sources.values()) source.dispose();
      sources.clear();
    },
  };
}

export function isEventStreamHost(value: unknown): value is EventStreamHost {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { kind?: unknown }).kind === 'eventStreamHost'
  );
}
