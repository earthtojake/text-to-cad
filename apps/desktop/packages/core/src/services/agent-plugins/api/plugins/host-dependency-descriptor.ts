import type { HostDependencyDefinition } from '#primitives/host-dependencies/api';
import type { CLIAgentPluginProvider } from './index';

export function buildDescriptorFromProvider(
  provider: CLIAgentPluginProvider
): HostDependencyDefinition {
  const { metadata, capabilities } = provider;
  const hostDep = capabilities.hostDependency;
  const binaryNames = hostDep.binaryNames;

  return {
    id: metadata.id,
    name: metadata.name,
    category: 'agent',
    binaryNames: binaryNames.length > 0 ? binaryNames : [metadata.id],
    installDocs: hostDep.installDocs ?? metadata.websiteUrl,
    installCommands: hostDep.installCommands,
    updateCommand: hostDep.updateCommand,
    status: 'active',
  };
}
