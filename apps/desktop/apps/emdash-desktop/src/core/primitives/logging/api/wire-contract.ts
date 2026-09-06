import { defineContract, procedure } from '@emdash/wire/rpc';
import { z } from 'zod';

export const loggingDomain = 'logging' as const;

export const loggingWireContract = defineContract({
  writeRendererLog: procedure({
    input: z.object({
      level: z.enum(['debug', 'info', 'warn', 'error']),
      source: z.literal('renderer'),
      input: z.array(z.unknown()),
    }),
    output: z.void(),
  }),
});

export type LoggingWireContract = typeof loggingWireContract;
