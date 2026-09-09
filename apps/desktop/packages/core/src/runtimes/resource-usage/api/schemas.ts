import { z } from 'zod';

const percentageSchema = z.number().min(0).max(100);

export const resourceUsageSampleSchema = z.object({
  cpu: z.object({
    usedPercent: percentageSchema,
  }),
  memory: z.object({
    usedPercent: percentageSchema,
    usedBytes: z.number().nonnegative(),
    totalBytes: z.number().nonnegative(),
  }),
  disk: z.object({
    usedPercent: percentageSchema,
    usedBytes: z.number().nonnegative(),
    totalBytes: z.number().nonnegative(),
    path: z.string().min(1),
  }),
  /** Epoch milliseconds at which the sample was collected. */
  collectedAt: z.number().int().nonnegative(),
});

export type ResourceUsageSample = z.infer<typeof resourceUsageSampleSchema>;
