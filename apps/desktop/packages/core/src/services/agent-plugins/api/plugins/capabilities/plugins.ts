import { definePluginCapability } from '@emdash/shared/plugins';
import z from 'zod';
import type { PluginFs } from '#primitives/plugin-fs/api';
import type { ConfigRootResolver } from '../helpers/config-root';

export type PluginScope = { kind: 'global' } | { kind: 'workspace'; path: string };

export type IPlugins = {
  resolveConfigRoot: ConfigRootResolver;
  /** Install the plugin and return the root-relative paths written. */
  installPlugin(fs: PluginFs, scope: PluginScope): Promise<string[]>;
  uninstallPlugin(fs: PluginFs, scope: PluginScope): Promise<void>;
  isPluginInstalled(fs: PluginFs, scope: PluginScope): Promise<boolean>;
  getPluginVersion(fs: PluginFs, scope: PluginScope): Promise<string>;
  getPluginPath(fs: PluginFs, scope: PluginScope): Promise<string>;
};

/**
 * PluginsDescriptor describes how an agent loads extension plugins.
 *
 * kind: 'file-drop' — emdash drops a file into the agent's plugin directory
 * kind: 'cli'       — emdash invokes the agent's CLI to install/manage plugins
 * kind: 'none'      — the agent does not support plugins
 */
export const pluginsCapability = definePluginCapability<IPlugins>()(
  'plugins',
  z.discriminatedUnion('kind', [
    z.object({
      kind: z.literal('file-drop'),
      scope: z.enum(['global', 'workspace']),
    }),
    z.object({ kind: z.literal('cli') }),
    z.object({ kind: z.literal('none') }),
  ]),
  { kind: 'none' }
);
