import type { PluginFs } from '#primitives/plugin-fs/api';
import type { ITrustBehavior } from '#services/agent-plugins/api/plugins/capabilities/trust';

export type JsonConfigTrustBehaviorOptions = {
  configName: string;
  withTrustedPath: (
    config: Record<string, unknown>,
    workspacePath: string
  ) => Record<string, unknown> | null;
};

export function buildJsonConfigTrustBehavior({
  configName,
  withTrustedPath,
}: JsonConfigTrustBehaviorOptions): ITrustBehavior {
  return {
    async trustWorkspace(fs: PluginFs, ctx): Promise<void> {
      const config = parseConfig(await fs.read(configName), configName);

      const nextConfig = withTrustedPath(config, ctx.workspacePath);
      if (!nextConfig) return;

      await fs.write(configName, JSON.stringify(nextConfig, null, 2) + '\n');
    },
  };
}

function parseConfig(raw: string | null, configName: string): Record<string, unknown> {
  if (!raw || raw.trim() === '') return {};

  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch (error: unknown) {
    throw new Error(`refusing to overwrite corrupt config ${configName}: ${String(error)}`);
  }

  if (!isPlainObject(parsed)) {
    throw new Error(`refusing to overwrite non-object config root in ${configName}`);
  }
  return parsed;
}

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}
