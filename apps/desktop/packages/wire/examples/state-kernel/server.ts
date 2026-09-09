import { ok } from '@emdash/shared';
import {
  createController,
  defineContract,
  liveModel,
  liveState,
  mutation,
  type Controller,
} from '@emdash/wire/rpc';
import { cell, expose, family, type ExposeOptions } from '@emdash/wire/state';
import { z } from 'zod';

export const api = defineContract({
  counter: liveModel({
    key: z.object({ id: z.string() }),
    states: {
      value: liveState({ data: z.object({ count: z.number() }) }),
    },
    mutations: {
      increment: mutation({
        input: z.object({ by: z.number() }),
        data: z.void(),
        error: z.never(),
      }),
    },
  }),
});

// The authoritative state lives in kernel cells: one per counter id.
const counters = family((_id: string) => cell({ count: 0 }));

// `expose` bridges kernel state onto the live model endpoint: each contract
// state resolves to a readable, and each mutation updates the cells and awaits
// the observed revision so the client's cursor settles.
export function createCounterProvider(options: Pick<ExposeOptions<typeof api.counter>, 'scope'>) {
  return expose(
    api.counter,
    { value: (key) => counters(key.id) },
    {
      ...options,
      mutations: {
        async increment(context) {
          const revision = counters(context.key.id).update(
            (previous) => ({ count: previous.count + context.input.by }),
            { mutationIds: [context.mutationId] }
          );
          await context.observed('value', revision);
          return ok<void>();
        },
      },
    }
  );
}

export function createCounterController(
  provider: ReturnType<typeof createCounterProvider>
): Controller {
  return createController(api, { counter: provider });
}
