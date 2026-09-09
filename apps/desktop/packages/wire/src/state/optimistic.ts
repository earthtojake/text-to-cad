import { err, ok, type Result } from '@emdash/shared';
import { systemClock, type Clock, type TimerHandle } from '@emdash/shared/scheduling';
import { cell, derived, snapshot, type Readable } from './core';
import { produce } from './live-immer';

export type PendingHandle = {
  readonly mutationId: string;
  drop(): void;
};

export type ContractMutationInvocation<D, E> = {
  result: Result<D, E>;
  settled: Promise<void>;
};

export interface OptimisticView<T> extends Readable<T | undefined> {
  apply(
    recipe: (draft: T) => void,
    options: {
      mutationId: string;
      ttlMs?: number;
    }
  ): PendingHandle;
  run<I, D, E>(
    mutation: (
      input: I,
      options: { mutationId: string }
    ) => Promise<ContractMutationInvocation<D, E>>,
    input: I,
    recipe: (draft: T, input: I) => void
  ): Promise<Result<D, E>>;
}

type PendingPatch<T> = {
  mutationId: string;
  recipe: (draft: T) => void;
  timer: TimerHandle | undefined;
  generation: number | undefined;
};

export type OptimisticOptions = {
  ttlMs?: number;
  clock?: Clock;
};

export function optimistic<T>(
  base: Readable<T | undefined>,
  options: OptimisticOptions = {}
): OptimisticView<T> {
  const clock = options.clock ?? systemClock;
  const pending = cell<readonly PendingPatch<T>[]>([]);

  const view = derived(() => {
    const baseSnapshot = snapshot(base);
    const value = baseSnapshot.value;
    if (value === undefined) return undefined;
    const acknowledged = new Set(baseSnapshot.mutationIds ?? []);
    const generation = baseSnapshot.generation;
    const patches = snapshot(pending).value;
    const current = patches.filter((patch) => {
      if (acknowledged.has(patch.mutationId)) return false;
      return patch.generation === generation;
    });
    return current.reduce(
      (model: T, patch: PendingPatch<T>) => produce(model, patch.recipe),
      value
    );
  }) as OptimisticView<T>;

  view.apply = (recipe, applyOptions) => {
    const timer = clock.schedule(
      applyOptions.ttlMs ?? options.ttlMs ?? 30_000,
      () => {
        remove(applyOptions.mutationId);
      },
      { unref: true }
    );
    pending.update((patches) => [
      ...patches,
      {
        mutationId: applyOptions.mutationId,
        recipe,
        timer,
        generation: snapshot(base).generation,
      },
    ]);
    return {
      mutationId: applyOptions.mutationId,
      drop() {
        remove(applyOptions.mutationId);
      },
    };
  };

  view.run = async (mutation, input, recipe) => {
    const mutationId = crypto.randomUUID();
    const handle = view.apply((draft) => recipe(draft, input), { mutationId });
    try {
      const invocation = await mutation(input, { mutationId });
      if (!invocation.result.success) {
        handle.drop();
        return err(invocation.result.error);
      }
      await invocation.settled;
      handle.drop();
      return ok(invocation.result.data);
    } catch (error) {
      handle.drop();
      throw error;
    }
  };

  return view;

  function remove(mutationId: string): void {
    pending.update((patches) => {
      const next = patches.filter((patch) => patch.mutationId !== mutationId);
      for (const patch of patches) {
        if (patch.mutationId === mutationId) patch.timer?.dispose();
      }
      return next;
    });
  }
}
