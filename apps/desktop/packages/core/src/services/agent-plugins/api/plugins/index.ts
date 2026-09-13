import {
  createPluginFramework,
  iconAsset,
  type AssetDescriptors,
  type CapabilityBehaviors,
  type CapabilityDescriptors,
  type ResolvedCapabilityDescriptors,
} from '@emdash/shared/plugins';
import z from 'zod';
import { hostDependencyCapability } from '#primitives/host-dependencies/api';
import { acpCapability } from '#services/agent-plugins/api/plugins/capabilities/acp';
import { authCapability } from '#services/agent-plugins/api/plugins/capabilities/auth';
import { autoApproveCapability } from '#services/agent-plugins/api/plugins/capabilities/auto-approve';
import { effortCapability } from '#services/agent-plugins/api/plugins/capabilities/effort';
import { hooksCapability } from '#services/agent-plugins/api/plugins/capabilities/hooks';
import { mcpCapability } from '#services/agent-plugins/api/plugins/capabilities/mcp';
import { modelsCapability } from '#services/agent-plugins/api/plugins/capabilities/models';
import { pluginsCapability } from '#services/agent-plugins/api/plugins/capabilities/plugins';
import { promptCapability } from '#services/agent-plugins/api/plugins/capabilities/prompt';
import { sessionsCapability } from '#services/agent-plugins/api/plugins/capabilities/sessions';
import { trustCapability } from '#services/agent-plugins/api/plugins/capabilities/trust';

export const PLUGIN_CAPABILITIES = {
  acp: acpCapability,
  auth: authCapability,
  autoApprove: autoApproveCapability,
  effort: effortCapability,
  hooks: hooksCapability,
  hostDependency: hostDependencyCapability,
  mcp: mcpCapability,
  models: modelsCapability,
  plugins: pluginsCapability,
  prompt: promptCapability,
  sessions: sessionsCapability,
  trust: trustCapability,
} as const;

export type Capabilities = typeof PLUGIN_CAPABILITIES;

export const PLUGIN_ASSETS = {
  icon: iconAsset,
} as const;

export type Assets = typeof PLUGIN_ASSETS;

const metadataSchema = z.object({
  id: z.string(),
  name: z.string(),
  description: z.string(),
  websiteUrl: z.string(),
  compatibleVersions: z.string().optional(),
});

export type CLIAgentPluginMetadata = z.infer<typeof metadataSchema>;

export type CLIAgentPluginDefinition = {
  metadata: CLIAgentPluginMetadata;
  capabilities: ResolvedCapabilityDescriptors<Capabilities>;
  assets: AssetDescriptors<Assets>;
  validate(): z.ZodError[];
};

export type CLIAgentPluginProvider = CLIAgentPluginDefinition & {
  behavior: CapabilityBehaviors<Capabilities>;
};

const pluginFramework = createPluginFramework(PLUGIN_CAPABILITIES, metadataSchema, PLUGIN_ASSETS);

export const definePlugin: (
  metadata: CLIAgentPluginMetadata,
  capabilities: CapabilityDescriptors<Capabilities>,
  assets: AssetDescriptors<Assets>
) => CLIAgentPluginDefinition = pluginFramework.definePlugin;

export const registerPluginBehavior: (
  plugin: CLIAgentPluginDefinition,
  behavior: CapabilityBehaviors<Capabilities>
) => CLIAgentPluginProvider = pluginFramework.registerPluginBehavior;

// Convenience re-exports for impl packages
export type {
  AgentCommand,
  CommandContext,
} from '#services/agent-plugins/api/plugins/capabilities/prompt';
export type {
  CanonicalHookEvent,
  HookEvent,
  HookRegistration,
  NotificationType,
} from '#services/agent-plugins/api/plugins/capabilities/hooks-types';
export type { PluginFs } from '#primitives/plugin-fs/api';
// Capability behavior interfaces — needed for dts portability
export type {
  IAcpBehavior,
  AcpSpawnContext,
  AcpSpawnResult,
  AcpProcessIo,
  AcpAgentApi,
  AcpClientFactory,
} from '#services/agent-plugins/api/plugins/capabilities/acp';
export { agentAuthStatusSchema } from '#services/agent-plugins/api/plugins/capabilities/auth';
export type {
  AgentAuthContext,
  AgentAuthDescriptor,
  AgentAuthMethod,
  AgentAuthStatus,
  IAgentAuthBehavior,
} from '#services/agent-plugins/api/plugins/capabilities/auth';
export type { IHostDependencyBehavior } from '#primitives/host-dependencies/api';
export type { IHooksBehavior } from '#services/agent-plugins/api/plugins/capabilities/hooks';
export type {
  IMcpBehavior,
  McpServerRegistration,
} from '#services/agent-plugins/api/plugins/capabilities/mcp';
export type { IPlugins } from '#services/agent-plugins/api/plugins/capabilities/plugins';
export type { ISessionsBehavior } from '#services/agent-plugins/api/plugins/capabilities/sessions';
export type {
  ITrustBehavior,
  TrustContext,
} from '#services/agent-plugins/api/plugins/capabilities/trust';
export { AgentPluginHost } from './plugin-host';
export { buildDescriptorFromProvider } from './host-dependency-descriptor';
export type {
  AgentHostAcpSpawn,
  AgentHostDeps,
  AgentHostError,
  AgentHostLoginCommand,
  ResolvedAcpProvider,
  ResolvedAuthProvider,
  ResolvedTuiProvider,
} from './plugin-host';

// Typed registry factory
export { createPluginRegistry, type PluginRegistry } from '@emdash/shared/plugins';
