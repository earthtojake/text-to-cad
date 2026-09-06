import { createEmitter, ok, type Result, type Unsubscribe } from '@emdash/shared';

export type MachineEvolveResult<State, Effect> = {
  state: State;
  effects?: readonly Effect[];
};

export type MachineDefinition<State, Command, Event, Effect, CommandError, Context = void> = {
  decide(state: State, command: Command, context: Context): Result<readonly Event[], CommandError>;
  evolve(state: State, event: Event): MachineEvolveResult<State, Effect>;
  validate?(state: State): void;
};

export type MachineBatchTrigger<Command, Event> =
  | { kind: 'dispatch'; command: Command }
  | { kind: 'apply'; events: readonly Event[] }
  | { kind: 'replace' };

export type MachineBatch<State, Command, Event, Effect> = {
  previous: State;
  state: State;
  events: readonly Event[];
  effects: readonly Effect[];
  changed: boolean;
  trigger: MachineBatchTrigger<Command, Event>;
};

export type MachineOptions<State, Command, Event, Effect> = {
  onBatch?: (batch: MachineBatch<State, Command, Event, Effect>) => void;
  onSubscriberError?: (error: unknown) => void;
};

export type Machine<State, Command, Event, Effect, CommandError, Context = void> = {
  current(): State;
  dispatch(command: Command, context: Context): Result<readonly Effect[], CommandError>;
  apply(...events: readonly Event[]): readonly Effect[];
  replace(state: State): void;
  subscribe(listener: (batch: MachineBatch<State, Command, Event, Effect>) => void): Unsubscribe;
  dispose(): void;
};

export function createMachine<State, Command, Event, Effect, CommandError, Context = void>(
  definition: MachineDefinition<State, Command, Event, Effect, CommandError, Context>,
  initialState: State,
  options: MachineOptions<State, Command, Event, Effect> = {}
): Machine<State, Command, Event, Effect, CommandError, Context> {
  let state = initialState;
  let disposed = false;
  const batches = createEmitter<MachineBatch<State, Command, Event, Effect>>({
    onSubscriberError: ({ error }) => options.onSubscriberError?.(error),
  });

  definition.validate?.(state);

  const assertOpen = () => {
    if (disposed) {
      throw new Error('Machine is disposed');
    }
  };

  const publish = (batch: MachineBatch<State, Command, Event, Effect>) => {
    options.onBatch?.(batch);
    batches.emit(batch);
  };

  const fold = (
    events: readonly Event[],
    trigger: MachineBatchTrigger<Command, Event>
  ): readonly Effect[] => {
    assertOpen();
    if (events.length === 0) return [];

    const previous = state;
    const effects: Effect[] = [];

    for (const event of events) {
      const result = definition.evolve(state, event);
      definition.validate?.(result.state);
      state = result.state;
      effects.push(...(result.effects ?? []));
    }

    const batch = {
      previous,
      state,
      events,
      effects,
      changed: !Object.is(previous, state),
      trigger,
    } satisfies MachineBatch<State, Command, Event, Effect>;
    publish(batch);
    return effects;
  };

  return {
    current() {
      return state;
    },

    dispatch(command, context) {
      assertOpen();
      const decision = definition.decide(state, command, context);
      if (!decision.success) return decision;
      return ok(fold(decision.data, { kind: 'dispatch', command }));
    },

    apply(...events) {
      return fold(events, { kind: 'apply', events });
    },

    replace(next) {
      assertOpen();
      definition.validate?.(next);
      const previous = state;
      state = next;
      publish({
        previous,
        state,
        events: [],
        effects: [],
        changed: !Object.is(previous, state),
        trigger: { kind: 'replace' },
      });
    },

    subscribe(listener) {
      assertOpen();
      return batches.subscribe(listener);
    },

    dispose() {
      if (disposed) return;
      disposed = true;
      batches.clear();
    },
  };
}
