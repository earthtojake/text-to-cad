import { definePluginCapability } from '@emdash/shared/plugins';
import z from 'zod';
import type { PluginFs } from '#primitives/plugin-fs/api';

const cliLoginMethodSchema = z.object({
  kind: z.literal('cli-login'),
  id: z.string(),
  name: z.string(),
  args: z.array(z.string()),
  description: z.string().optional(),
});

const apiKeyEnvVarSchema = z.object({
  name: z.string(),
  label: z.string(),
});

const apiKeyMethodSchema = z.object({
  kind: z.literal('api-key'),
  id: z.string(),
  name: z.string(),
  envVars: z.array(apiKeyEnvVarSchema).min(1),
  helpUrl: z.string().optional(),
});

const authMethodSchema = z.discriminatedUnion('kind', [cliLoginMethodSchema, apiKeyMethodSchema]);

export const agentAuthDescriptorSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('none'),
  }),
  z.object({
    kind: z.literal('supported'),
    methods: z.array(authMethodSchema).min(1),
  }),
]);

export type AgentAuthMethod = z.infer<typeof authMethodSchema>;
export type AgentAuthDescriptor = z.infer<typeof agentAuthDescriptorSchema>;

export const agentAuthStatusSchema = z.discriminatedUnion('kind', [
  z.object({
    kind: z.literal('authenticated'),
    account: z.string().optional(),
  }),
  z.object({
    kind: z.literal('unauthenticated'),
    message: z.string().optional(),
  }),
  z.object({
    kind: z.literal('unknown'),
    message: z.string().optional(),
  }),
]);

export type AgentAuthStatus =
  | { kind: 'authenticated'; account?: string }
  | { kind: 'unauthenticated'; message?: string }
  | { kind: 'unknown'; message?: string };

export type AgentAuthContext = {
  cli: string;
  exec: (
    command: string,
    args?: string[],
    opts?: { timeout?: number; maxBuffer?: number; signal?: AbortSignal }
  ) => Promise<{ stdout: string; stderr: string }>;
  fs: PluginFs;
  env: Record<string, string>;
};

export type IAgentAuthBehavior = {
  checkStatus(ctx: AgentAuthContext): Promise<AgentAuthStatus>;
  buildLoginCommand?(
    ctx: { cli: string },
    methodId: string
  ): { command: string; args: string[] } | null;
};

export const authCapability = definePluginCapability<IAgentAuthBehavior>()(
  'auth',
  agentAuthDescriptorSchema,
  { kind: 'none' },
  {
    requiresBehavior: (descriptor) => descriptor.kind === 'supported',
  }
);
