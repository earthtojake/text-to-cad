import { hostRefSchema } from '@emdash/core/primitives/host/api';
import { modelOptionSchema } from '@emdash/core/runtimes/acp/api';
import {
  agentConfigAuthErrorSchema,
  agentConfigContract,
  agentConfigListSchema,
  hooksStatusSchema,
} from '@emdash/core/runtimes/agent-config/api';
// The auth capability module directly: the plugins barrel drags in the plugin
// host and its node-only dependencies, which this isomorphic contract must not.
import { agentAuthStatusSchema } from '@emdash/core/services/agent-plugins/api/plugins/capabilities/auth';
import { hostDependencyOperationProgressSchema } from '@emdash/core/services/host-dependencies/api';
import { runtimeResolveErrorSchema } from '@emdash/core/services/runtime-broker/api';
import type { Result } from '@emdash/shared';
import {
  defineContract,
  fallible,
  liveJob,
  liveLog,
  liveModel,
  liveState,
  procedure,
} from '@emdash/wire/rpc';
import { z } from 'zod';
import type {
  AgentInstallationStatus,
  AgentInstallError,
  AgentMetadata,
  AgentPayload,
  AgentSettings,
  AgentUninstallError,
  AgentUpdateError,
  InstallMethod,
} from '@core/primitives/agents/api';
import type { ProviderCustomConfig } from '@core/primitives/app-settings/api';

const hostInputSchema = z.object({ host: hostRefSchema });
const agentInputSchema = hostInputSchema.extend({ id: z.string() });
const providerInputSchema = hostInputSchema.extend({ providerId: z.string() });
const agentsAuthErrorSchema = z.union([agentConfigAuthErrorSchema, runtimeResolveErrorSchema]);

export const agentsDomain = 'agents' as const;

export const agentsContract = defineContract({
  discoverModels: fallible({
    input: providerInputSchema,
    data: z.array(modelOptionSchema),
    error: runtimeResolveErrorSchema,
  }),
  // Static plugin-registry metadata (icons, display names); identical on every host.
  listMetadata: procedure({ input: z.void(), output: z.custom<AgentMetadata[]>() }),
  list: fallible({
    input: hostInputSchema,
    data: z.custom<AgentPayload[]>(),
    error: runtimeResolveErrorSchema,
  }),
  get: fallible({
    input: agentInputSchema,
    data: z.custom<AgentPayload | null>(),
    error: runtimeResolveErrorSchema,
  }),
  listAgentInstallationStatus: fallible({
    input: hostInputSchema,
    data: z.custom<AgentInstallationStatus[]>(),
    error: runtimeResolveErrorSchema,
  }),
  install: liveJob({
    input: agentInputSchema.extend({
      method: z.custom<InstallMethod>().optional(),
      elevate: z.boolean().optional(),
    }),
    progress: hostDependencyOperationProgressSchema,
    result: z.custom<AgentInstallationStatus>(),
    error: z.union([z.custom<AgentInstallError>(), runtimeResolveErrorSchema]),
  }),
  update: liveJob({
    input: agentInputSchema.extend({
      method: z.custom<InstallMethod>().optional(),
      elevate: z.boolean().optional(),
    }),
    progress: hostDependencyOperationProgressSchema,
    result: z.custom<AgentInstallationStatus>(),
    error: z.union([z.custom<AgentUpdateError>(), runtimeResolveErrorSchema]),
  }),
  uninstall: fallible({
    input: agentInputSchema.extend({ method: z.custom<InstallMethod>().optional() }),
    data: z.custom<Result<AgentInstallationStatus, AgentUninstallError>>(),
    error: runtimeResolveErrorSchema,
  }),
  getDefaultSettings: fallible({
    input: agentInputSchema,
    data: z.custom<ProviderCustomConfig>(),
    error: runtimeResolveErrorSchema,
  }),
  getSettings: fallible({
    input: agentInputSchema,
    data: z.custom<AgentSettings>(),
    error: runtimeResolveErrorSchema,
  }),
  updateSettings: fallible({
    input: agentInputSchema.extend({ config: z.custom<Partial<ProviderCustomConfig>>() }),
    data: z.void(),
    error: runtimeResolveErrorSchema,
  }),
  setUsedInstallation: fallible({
    input: agentInputSchema.extend({ selection: z.unknown().optional() }),
    data: z.void(),
    error: runtimeResolveErrorSchema,
  }),
  probeOverride: fallible({
    input: agentInputSchema.extend({
      selection: z.object({ path: z.string().optional(), cli: z.string().optional() }),
    }),
    data: z.null(),
    error: runtimeResolveErrorSchema,
  }),
  refreshLatestVersion: fallible({
    input: agentInputSchema,
    data: z.void(),
    error: runtimeResolveErrorSchema,
  }),
  probeAll: fallible({
    input: hostInputSchema,
    data: z.void(),
    error: runtimeResolveErrorSchema,
  }),

  auth: liveModel({
    key: hostInputSchema,
    states: {
      list: liveState({ data: agentConfigListSchema }),
    },
  }),
  hooksStatus: fallible({
    input: agentConfigContract.hooksStatus.input.extend(hostInputSchema.shape),
    data: hooksStatusSchema,
    error: runtimeResolveErrorSchema,
  }),
  startLogin: fallible({
    input: agentConfigContract.startLogin.input.extend(hostInputSchema.shape),
    data: z.void(),
    error: agentsAuthErrorSchema,
  }),
  cancelLogin: fallible({
    input: providerInputSchema,
    data: z.void(),
    error: agentsAuthErrorSchema,
  }),
  sendLoginInput: fallible({
    input: agentConfigContract.sendLoginInput.input.extend(hostInputSchema.shape),
    data: z.void(),
    error: agentsAuthErrorSchema,
  }),
  resizeLogin: fallible({
    input: agentConfigContract.resizeLogin.input.extend(hostInputSchema.shape),
    data: z.void(),
    error: agentsAuthErrorSchema,
  }),
  markUrlHandled: fallible({
    input: agentConfigContract.markUrlHandled.input.extend(hostInputSchema.shape),
    data: z.void(),
    error: agentsAuthErrorSchema,
  }),
  refreshAuthStatus: fallible({
    input: providerInputSchema,
    data: agentAuthStatusSchema,
    error: agentsAuthErrorSchema,
  }),
  loginOutput: liveLog({
    key: providerInputSchema,
  }),
});

export type AgentsContract = typeof agentsContract;
