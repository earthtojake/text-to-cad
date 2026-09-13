import { defineContract, fallible } from '@emdash/wire/rpc';
import { z } from 'zod';

export const portForwardFamilySchema = z.enum(['ipv4', 'ipv6']);

export const portForwardInspectInputSchema = z.object({
  port: z.number().int().min(1).max(65535),
});

export const portForwardInspectResultSchema = z.object({
  listening: z.boolean(),
  families: z.array(portForwardFamilySchema),
});

export const portForwardInspectErrorSchema = z.object({
  type: z.literal('io'),
  message: z.string(),
});

export const portForwardsContract = defineContract({
  inspect: fallible({
    input: portForwardInspectInputSchema,
    data: portForwardInspectResultSchema,
    error: portForwardInspectErrorSchema,
  }),
});

export type PortForwardsContract = typeof portForwardsContract;
