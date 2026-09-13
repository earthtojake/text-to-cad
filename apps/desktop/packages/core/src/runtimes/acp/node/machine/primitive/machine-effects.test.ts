import { describe, expect, it, vi } from 'vitest';
import { createMachineEffectDriver } from './machine-effects';

type Effect =
  | { type: 'record'; value: string }
  | { type: 'enqueue'; value: string }
  | { type: 'throw'; value: string };

describe('createMachineEffectDriver', () => {
  it('drains effects in FIFO order', () => {
    const seen: string[] = [];
    const driver = createMachineEffectDriver<Effect>({
      interpret(effect) {
        if (effect.type === 'record') seen.push(effect.value);
      },
    });

    driver.run([
      { type: 'record', value: 'a' },
      { type: 'record', value: 'b' },
    ]);

    expect(seen).toEqual(['a', 'b']);
  });

  it('queues reentrant effects without recursive delivery', () => {
    const seen: string[] = [];
    const driver = createMachineEffectDriver<Effect>({
      interpret(effect, context) {
        seen.push(effect.value);
        if (effect.type === 'enqueue') {
          context.run([
            { type: 'record', value: `${effect.value}:child-1` },
            { type: 'record', value: `${effect.value}:child-2` },
          ]);
        }
      },
    });

    driver.run([
      { type: 'enqueue', value: 'a' },
      { type: 'record', value: 'b' },
    ]);

    expect(seen).toEqual(['a', 'b', 'a:child-1', 'a:child-2']);
  });

  it('reports interpreter errors and continues draining', () => {
    const seen: string[] = [];
    const errors: unknown[] = [];
    const driver = createMachineEffectDriver<Effect>({
      interpret(effect) {
        if (effect.type === 'throw') throw new Error(effect.value);
        seen.push(effect.value);
      },
      onInterpreterError: ({ error }) => errors.push(error),
    });

    driver.run([
      { type: 'record', value: 'before' },
      { type: 'throw', value: 'boom' },
      { type: 'record', value: 'after' },
    ]);

    expect(seen).toEqual(['before', 'after']);
    expect(errors).toHaveLength(1);
    expect(errors[0]).toBeInstanceOf(Error);
  });

  it('emits one drain summary for nested work', () => {
    const drains = vi.fn();
    const driver = createMachineEffectDriver<Effect>({
      interpret(effect, context) {
        if (effect.type === 'enqueue') {
          context.run([{ type: 'record', value: 'child' }]);
        }
      },
      onDrain: drains,
    });

    driver.run([{ type: 'enqueue', value: 'parent' }]);

    expect(drains).toHaveBeenCalledOnce();
    expect(drains).toHaveBeenCalledWith({
      effects: [
        { type: 'enqueue', value: 'parent' },
        { type: 'record', value: 'child' },
      ],
    });
  });

  it('drops queued effects after disposal', () => {
    const seen: string[] = [];
    const driver = createMachineEffectDriver<Effect>({
      interpret(effect, context) {
        seen.push(effect.value);
        if (effect.type === 'enqueue') {
          context.run([{ type: 'record', value: 'child' }]);
          driver.dispose();
        }
      },
    });

    driver.run([{ type: 'enqueue', value: 'parent' }]);

    expect(seen).toEqual(['parent']);
    expect(() => driver.run([{ type: 'record', value: 'after' }])).toThrow(
      'Machine effect driver is disposed'
    );
  });
});
