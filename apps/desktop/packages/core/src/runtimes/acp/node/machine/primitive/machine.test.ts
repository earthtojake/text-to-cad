import { err, ok } from '@emdash/shared';
import { describe, expect, it, vi } from 'vitest';
import { createMachine, type MachineDefinition } from './machine';

type State = {
  count: number;
  label: string;
};

type Command =
  | { type: 'increment'; by: number }
  | { type: 'rename'; label: string }
  | { type: 'double' }
  | { type: 'noop' }
  | { type: 'reject' };

type Event = { type: 'Incremented'; by: number } | { type: 'Renamed'; label: string };

type Effect = { type: 'changed'; count: number } | { type: 'renamed'; label: string };
type CommandError = { type: 'rejected' };

const definition: MachineDefinition<State, Command, Event, Effect, CommandError> = {
  decide(_state, command) {
    switch (command.type) {
      case 'increment':
        return ok([{ type: 'Incremented', by: command.by }]);
      case 'rename':
        return ok([{ type: 'Renamed', label: command.label }]);
      case 'double':
        return ok([
          { type: 'Incremented', by: 1 },
          { type: 'Incremented', by: 1 },
        ]);
      case 'noop':
        return ok([]);
      case 'reject':
        return err({ type: 'rejected' });
    }
  },
  evolve(state, event) {
    switch (event.type) {
      case 'Incremented': {
        const next = { ...state, count: state.count + event.by };
        return { state: next, effects: [{ type: 'changed', count: next.count }] };
      }
      case 'Renamed':
        return {
          state: { ...state, label: event.label },
          effects: [{ type: 'renamed', label: event.label }],
        };
    }
  },
  validate(state) {
    if (state.count < 0) {
      throw new Error('count must be non-negative');
    }
  },
};

describe('createMachine', () => {
  it('folds decided events and accumulates effects', () => {
    const onBatch = vi.fn();
    const machine = createMachine(definition, { count: 0, label: 'initial' }, { onBatch });

    const result = machine.dispatch({ type: 'double' }, undefined);

    expect(result).toEqual(
      ok([
        { type: 'changed', count: 1 },
        { type: 'changed', count: 2 },
      ])
    );
    expect(machine.current()).toEqual({ count: 2, label: 'initial' });
    expect(onBatch).toHaveBeenCalledTimes(1);
    expect(onBatch).toHaveBeenCalledWith(
      expect.objectContaining({
        previous: { count: 0, label: 'initial' },
        state: { count: 2, label: 'initial' },
        events: [
          { type: 'Incremented', by: 1 },
          { type: 'Incremented', by: 1 },
        ],
        changed: true,
      })
    );
  });

  it('leaves state unchanged when decide rejects', () => {
    const onBatch = vi.fn();
    const machine = createMachine(definition, { count: 0, label: 'initial' }, { onBatch });

    expect(machine.dispatch({ type: 'reject' }, undefined)).toEqual(err({ type: 'rejected' }));
    expect(machine.current()).toEqual({ count: 0, label: 'initial' });
    expect(onBatch).not.toHaveBeenCalled();
  });

  it('does not emit a batch for zero decided events', () => {
    const onBatch = vi.fn();
    const machine = createMachine(definition, { count: 0, label: 'initial' }, { onBatch });

    expect(machine.dispatch({ type: 'noop' }, undefined)).toEqual(ok([]));
    expect(onBatch).not.toHaveBeenCalled();
  });

  it('applies external events', () => {
    const machine = createMachine(definition, { count: 0, label: 'initial' });

    expect(machine.apply({ type: 'Renamed', label: 'ready' })).toEqual([
      { type: 'renamed', label: 'ready' },
    ]);
    expect(machine.current()).toEqual({ count: 0, label: 'ready' });
  });

  it('notifies subscribers and isolates subscriber errors', () => {
    const errors: unknown[] = [];
    const machine = createMachine(
      definition,
      { count: 0, label: 'initial' },
      { onSubscriberError: (error) => errors.push(error) }
    );
    const subscriber = vi.fn(() => {
      throw new Error('subscriber failed');
    });

    machine.subscribe(subscriber);
    machine.apply({ type: 'Incremented', by: 1 });

    expect(subscriber).toHaveBeenCalledOnce();
    expect(errors).toHaveLength(1);
    expect(machine.current()).toEqual({ count: 1, label: 'initial' });
  });

  it('replaces state for hydration', () => {
    const onBatch = vi.fn();
    const machine = createMachine(definition, { count: 0, label: 'initial' }, { onBatch });

    machine.replace({ count: 3, label: 'restored' });

    expect(machine.current()).toEqual({ count: 3, label: 'restored' });
    expect(onBatch).toHaveBeenCalledWith(
      expect.objectContaining({
        previous: { count: 0, label: 'initial' },
        state: { count: 3, label: 'restored' },
        events: [],
        effects: [],
        trigger: { kind: 'replace' },
      })
    );
  });

  it('validates initial and transitioned states', () => {
    expect(() => createMachine(definition, { count: -1, label: 'bad' })).toThrow(
      'count must be non-negative'
    );

    const machine = createMachine(definition, { count: 0, label: 'initial' });
    expect(() => machine.apply({ type: 'Incremented', by: -1 })).toThrow(
      'count must be non-negative'
    );
  });

  it('rejects use after disposal', () => {
    const machine = createMachine(definition, { count: 0, label: 'initial' });
    machine.dispose();

    expect(() => machine.current()).not.toThrow();
    expect(() => machine.dispatch({ type: 'increment', by: 1 }, undefined)).toThrow(
      'Machine is disposed'
    );
  });
});
