import { defineContract, fallible } from '@emdash/wire/rpc';
import { z } from 'zod';
import { resourceUsageErrorSchema } from './errors';
import { resourceUsageSampleSchema } from './schemas';

export const resourceUsageContract = defineContract({
  sample: fallible({
    input: z.void().optional(),
    data: resourceUsageSampleSchema,
    error: resourceUsageErrorSchema,
  }),
});

export type ResourceUsageContract = typeof resourceUsageContract;
