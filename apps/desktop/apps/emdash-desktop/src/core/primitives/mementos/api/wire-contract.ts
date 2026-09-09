import { ok } from '@emdash/shared';
import { defineContract, fallible, liveModel, liveState, mutation } from '@emdash/wire/rpc';
import { z } from 'zod';
import { subjectSchema } from '@core/primitives/subjects/api';
import {
  mementoMutationErrorSchema,
  mementoModelKeySchema,
  mementoRowSchema,
  type MementoRow,
} from './schemas';

export const mementosDomain = 'mementos' as const;

export const mementosWireContract = defineContract({
  memento: liveModel({
    key: mementoModelKeySchema,
    states: {
      value: liveState({ data: mementoRowSchema.nullable() }),
    },
    mutations: {
      save: mutation(
        {
          input: mementoRowSchema,
          data: z.void(),
          error: mementoMutationErrorSchema,
        },
        (ctx, row) => {
          ctx.produce('value', () => row as MementoRow);
          return ok<void>();
        }
      ),
      reset: mutation(
        {
          input: z.void(),
          data: z.void(),
          error: mementoMutationErrorSchema,
        },
        (ctx) => {
          ctx.produce('value', () => null);
          return ok<void>();
        }
      ),
    },
  }),
  deleteBySubject: fallible({
    input: subjectSchema,
    data: z.object({ deleted: z.number().int().nonnegative() }),
    error: mementoMutationErrorSchema,
  }),
  deleteAll: fallible({
    input: z.void(),
    data: z.object({ deleted: z.number().int().nonnegative() }),
    error: mementoMutationErrorSchema,
  }),
  deleteOrphans: fallible({
    input: z.object({
      kind: z.string().min(1),
      validKeys: z.array(z.string()),
    }),
    data: z.object({ deleted: z.number().int().nonnegative() }),
    error: mementoMutationErrorSchema,
  }),
});

export type MementosWireContract = typeof mementosWireContract;
