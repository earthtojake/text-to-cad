import { defineContract, liveModel, liveState, procedure } from '@emdash/wire/rpc';
import { z } from 'zod';
import type { ConnectionTestResult, SshConfig, SshConfigHost } from '@core/primitives/ssh/api';

const voidInput = z.void();
const connectionInput = z.object({ connectionId: z.string() });
const connectionStateSchema = z.enum([
  'connecting',
  'connected',
  'reconnecting',
  'disconnected',
  'error',
]);
const sshHealthStateSchema = z.discriminatedUnion('status', [
  z.object({ status: z.literal('ok') }),
  z.object({ status: z.literal('degraded') }),
]);
const connectionRuntimeSchema = z.record(
  z.string(),
  z.object({
    state: connectionStateSchema,
    health: sshHealthStateSchema,
  })
);

export type SshConnectionsRuntime = z.infer<typeof connectionRuntimeSchema>;

export const sshDomain = 'ssh' as const;

export const sshContract = defineContract({
  connections: liveModel({
    key: z.void(),
    states: {
      runtime: liveState({ data: connectionRuntimeSchema }),
    },
  }),
  connect: procedure({ input: connectionInput, output: connectionStateSchema }),
  ensureConnected: procedure({ input: connectionInput, output: connectionStateSchema }),
  disconnect: procedure({ input: connectionInput, output: z.void() }),
  getSshConfigHosts: procedure({
    input: voidInput,
    output: z.array(z.custom<SshConfigHost>()),
  }),
  getSshConfigHost: procedure({
    input: z.object({ alias: z.string() }),
    output: z.custom<SshConfigHost>(),
  }),
  testConnection: procedure({
    input: z.custom<SshConfig & { password?: string; passphrase?: string }>(),
    output: z.custom<ConnectionTestResult>(),
  }),
});
