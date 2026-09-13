import type { PluginFs } from '#primitives/plugin-fs/api';
import type { PluginScope } from '#services/agent-plugins/api/plugins/capabilities/plugins';
import type { ConfigRootResolver } from './config-root';

export function createFileDropPlugin(opts: {
  resolveConfigRoot: ConfigRootResolver;
  relativePath: string;
  content: string | ((ctx: { platform: NodeJS.Platform }) => string);
}) {
  const getContent = typeof opts.content === 'string' ? () => opts.content as string : opts.content;
  const getManagedContent = (context: { platform: NodeJS.Platform }) =>
    `// emdash-hook-config-version:1\n${getContent(context)}`;

  return {
    resolveConfigRoot: opts.resolveConfigRoot,
    async installPlugin(fs: PluginFs, _scope: PluginScope): Promise<string[]> {
      const content = getManagedContent({ platform: process.platform });
      await fs.write(opts.relativePath, content);
      return [opts.relativePath];
    },
    async uninstallPlugin(fs: PluginFs, _scope: PluginScope): Promise<void> {
      await fs.delete(opts.relativePath);
    },
    async isPluginInstalled(fs: PluginFs, _scope: PluginScope): Promise<boolean> {
      const current = await fs.read(opts.relativePath);
      return current === getManagedContent({ platform: process.platform });
    },
    async getPluginVersion(_fs: PluginFs, _scope: PluginScope): Promise<string> {
      return '1.0.0';
    },
    async getPluginPath(_fs: PluginFs, _scope: PluginScope): Promise<string> {
      return opts.relativePath;
    },
  };
}
