import type {
  CLIAgentPluginMetadata,
  CLIAgentPluginProvider,
} from '@emdash/core/services/agent-plugins/api/plugins';
import { asAgentProviderId, pluginRegistry, type AgentProviderId } from '@emdash/plugins/agents';

export function getPlugin(id: string): CLIAgentPluginProvider {
  const plugin = pluginRegistry.get(id);
  if (!plugin) throw new Error(`No plugin found for provider: ${id}`);
  return plugin;
}

export function getPluginMetadata(id: string): CLIAgentPluginMetadata {
  const plugin = pluginRegistry.get(id);
  if (!plugin) throw new Error(`No plugin metadata found for provider: ${id}`);
  return plugin.metadata;
}

export function listPlugins(): CLIAgentPluginProvider[] {
  return pluginRegistry.getAll();
}

export function isValidProviderId(value: unknown): value is AgentProviderId {
  return typeof value === 'string' && pluginRegistry.get(value) !== undefined;
}

export function toAgentProviderId(value: string): AgentProviderId {
  if (!isValidProviderId(value)) throw new Error(`Unknown agent provider: ${value}`);
  return asAgentProviderId(value);
}
