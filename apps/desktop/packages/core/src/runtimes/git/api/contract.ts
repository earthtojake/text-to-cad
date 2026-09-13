import { defineContract, fallible, liveJob } from '@emdash/wire/rpc';
import { z } from 'zod';
import { hostAbsolutePathSchema } from '#primitives/path/api';
import { gitCheckoutContract } from '#runtimes/git/api/checkout/contract';
import { gitRepositoryContract } from '#runtimes/git/api/repository/contract';
import {
  cloneRepositoryErrorSchema,
  ensureRepositoryErrorSchema,
  inspectPathErrorSchema,
} from './errors';
import {
  cloneRepositoryJobInputSchema,
  ensureRepositoryOptionsSchema,
  gitPathInspectionSchema,
  gitRepositoryInfoSchema,
  transferProgressSchema,
} from './schemas';

export const gitContract = defineContract({
  inspectPath: fallible({
    input: z.object({ path: hostAbsolutePathSchema }),
    data: gitPathInspectionSchema,
    error: inspectPathErrorSchema,
  }),
  ensureRepository: fallible({
    input: z.object({
      path: hostAbsolutePathSchema,
      options: ensureRepositoryOptionsSchema.optional(),
    }),
    data: gitRepositoryInfoSchema,
    error: ensureRepositoryErrorSchema,
  }),
  cloneRepository: liveJob({
    input: cloneRepositoryJobInputSchema,
    progress: transferProgressSchema,
    result: gitRepositoryInfoSchema,
    error: cloneRepositoryErrorSchema,
  }),

  repository: gitRepositoryContract,
  checkout: gitCheckoutContract,
});

export type GitContract = typeof gitContract;
