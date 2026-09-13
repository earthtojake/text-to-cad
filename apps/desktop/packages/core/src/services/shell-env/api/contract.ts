import { defineContract, procedure } from '@emdash/wire/rpc';
import { z } from 'zod';

export const userShellEnvSchema = z.record(z.string(), z.string());

/** Parent-owned source of the latest captured user-shell environment. */
export const userShellEnvContract = defineContract({
  get: procedure({
    input: z.void().optional(),
    output: userShellEnvSchema,
  }),
});

export type UserShellEnv = z.output<typeof userShellEnvSchema>;
export type UserShellEnvContract = typeof userShellEnvContract;
