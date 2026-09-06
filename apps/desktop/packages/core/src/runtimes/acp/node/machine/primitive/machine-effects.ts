export type MachineEffectDriverContext<Effect> = {
  run(effects: readonly Effect[]): void;
};

export type MachineEffectDriverError<Effect> = {
  effect: Effect;
  error: unknown;
};

export type MachineEffectDrain<Effect> = {
  effects: readonly Effect[];
};

export type MachineEffectDriverOptions<Effect> = {
  interpret(effect: Effect, context: MachineEffectDriverContext<Effect>): void;
  onDrain?: (drain: MachineEffectDrain<Effect>) => void;
  onInterpreterError?: (error: MachineEffectDriverError<Effect>) => void;
};

export type MachineEffectDriver<Effect> = {
  run(effects: readonly Effect[]): void;
  dispose(): void;
};

export function createMachineEffectDriver<Effect>(
  options: MachineEffectDriverOptions<Effect>
): MachineEffectDriver<Effect> {
  const queue: Effect[] = [];
  let disposed = false;
  let draining = false;

  const assertOpen = () => {
    if (disposed) {
      throw new Error('Machine effect driver is disposed');
    }
  };

  const driver: MachineEffectDriver<Effect> = {
    run(effects) {
      assertOpen();
      if (effects.length === 0) return;
      queue.push(...effects);
      drain();
    },

    dispose() {
      disposed = true;
      queue.length = 0;
    },
  };

  const context: MachineEffectDriverContext<Effect> = {
    run(effects) {
      driver.run(effects);
    },
  };

  function drain(): void {
    if (draining) return;
    draining = true;
    const drained: Effect[] = [];

    try {
      while (queue.length > 0 && !disposed) {
        const effect = queue.shift()!;
        drained.push(effect);
        try {
          options.interpret(effect, context);
        } catch (error) {
          options.onInterpreterError?.({ effect, error });
        }
      }
    } finally {
      draining = false;
      if (drained.length > 0) {
        options.onDrain?.({ effects: drained });
      }
    }
  }

  return driver;
}
