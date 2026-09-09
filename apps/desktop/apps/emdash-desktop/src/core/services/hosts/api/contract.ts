import { hostRefSchema } from '@emdash/core/primitives/host/api';
import { defineContract, liveModel, liveState, procedure } from '@emdash/wire/rpc';
import { z } from 'zod';
import { hostAvailabilityStateSchema } from './availability';

export const hostServerStatusSchema = z.enum([
  'not-installed',
  'stopped',
  'booting',
  'shutting-down',
  'healthy',
  'failed',
]);

export const hostServerStateSchema = z.object({
  status: hostServerStatusSchema,
  version: z.string().optional(),
  latestVersion: z.string().optional(),
  updateAvailable: z.boolean().optional(),
  startedAt: z.number().optional(),
  detail: z.string().optional(),
  error: z
    .object({
      code: z.string(),
      message: z.string(),
    })
    .optional(),
});

const hostServerRuntimeSchema = z.record(z.string(), hostServerStateSchema);
const connectionInputSchema = z.object({ connectionId: z.string().min(1) });
const remoteHostRefSchema = hostRefSchema.transform((host, context) => {
  if (host.type === 'remote') return { type: 'remote' as const, id: host.id };
  context.addIssue({ code: 'custom', message: 'A remote Host is required' });
  return z.NEVER;
});
const refreshServerStateInputSchema = connectionInputSchema.extend({
  force: z.boolean().optional(),
});
const requestReadyInputSchema = z.object({
  host: hostRefSchema,
  cause: z.enum(['connect', 'retry']),
});
const wakeInputSchema = z.object({
  cause: z.enum(['online', 'focus']),
});

export type HostServerStatus = z.infer<typeof hostServerStatusSchema>;
export type HostServerState = z.infer<typeof hostServerStateSchema>;
export type HostServerRuntime = z.infer<typeof hostServerRuntimeSchema>;

export function isServerUsable(state: HostServerState | undefined): boolean {
  return state?.status === 'healthy' && state.error === undefined;
}

export const hostsDomain = 'hosts' as const;

export const hostsContract = defineContract({
  availability: liveModel({
    key: z.object({ host: hostRefSchema }),
    states: {
      state: liveState({ data: hostAvailabilityStateSchema }),
    },
  }),
  disconnect: procedure({ input: z.object({ host: remoteHostRefSchema }), output: z.void() }),
  requestReady: procedure({ input: requestReadyInputSchema, output: z.void() }),
  wake: procedure({ input: wakeInputSchema, output: z.void() }),
  serverStates: liveModel({
    key: z.void(),
    states: {
      runtime: liveState({ data: hostServerRuntimeSchema }),
    },
  }),
  refreshServerState: procedure({ input: refreshServerStateInputSchema, output: z.void() }),
  installServer: procedure({ input: connectionInputSchema, output: z.void() }),
  startServer: procedure({ input: connectionInputSchema, output: z.void() }),
  stopServer: procedure({ input: connectionInputSchema, output: z.void() }),
  restartServer: procedure({ input: connectionInputSchema, output: z.void() }),
  updateServer: procedure({ input: connectionInputSchema, output: z.void() }),
});
