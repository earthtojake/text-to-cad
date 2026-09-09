import { z } from 'zod';

/** Collecting the host usage sample failed (CPU, memory, or disk stat read). */
export const sampleFailedErrorSchema = z.object({
  type: z.literal('sample-failed'),
  message: z.string().min(1),
});

export const resourceUsageErrorSchema = z.discriminatedUnion('type', [sampleFailedErrorSchema]);

export type ResourceUsageError = z.infer<typeof resourceUsageErrorSchema>;
