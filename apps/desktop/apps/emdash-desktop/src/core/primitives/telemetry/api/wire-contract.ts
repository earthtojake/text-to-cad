import { defineContract, procedure } from '@emdash/wire/rpc';
import { z } from 'zod';

export const telemetryDomain = 'telemetry' as const;

export const telemetryContract = defineContract({
  capture: procedure({
    input: z.object({
      event: z.string(),
      properties: z.record(z.string(), z.unknown()).optional(),
    }),
    output: z.void(),
  }),
  getStatus: procedure({
    input: z.void(),
    output: z.object({
      status: z.object({
        enabled: z.boolean(),
        envDisabled: z.boolean(),
        userOptOut: z.boolean(),
        hasKeyAndHost: z.boolean(),
        perf_sampled: z.boolean(),
        session_id: z.string().nullable(),
        instance_id: z.string().nullable(),
      }),
    }),
  }),
  setEnabled: procedure({ input: z.object({ enabled: z.boolean() }), output: z.void() }),
});
