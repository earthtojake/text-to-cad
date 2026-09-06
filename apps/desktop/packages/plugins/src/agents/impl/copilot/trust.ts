import { buildJsonConfigTrustBehavior } from '@emdash/core/services/agent-plugins/api/plugins/helpers';

function withCopilotTrustedFolder(
  config: Record<string, unknown>,
  workspacePath: string
): Record<string, unknown> | null {
  const trustedFolders = Array.isArray(config.trustedFolders) ? config.trustedFolders : [];
  if (trustedFolders.includes(workspacePath)) return null;

  return {
    ...config,
    trustedFolders: [...trustedFolders, workspacePath],
  };
}

export function buildCopilotTrustBehavior() {
  return buildJsonConfigTrustBehavior({
    configName: '.copilot/config.json',
    withTrustedPath: withCopilotTrustedFolder,
  });
}
