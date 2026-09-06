import type { Logger } from '@emdash/shared/logger';
import type { AgentPluginHost } from '#services/agent-plugins/api/plugins';
import type { PluginScope } from '#services/agent-plugins/api/plugins/capabilities/plugins';
import { createLocalPluginFs } from '#services/agent-plugins/api/plugins/helpers';

export type HookInstallationStatus = {
  state: 'installed' | 'pending-install';
  resolvedRoot: string;
};

export type AgentHookInstallerOptions = {
  agentHost: AgentPluginHost;
  logger: Logger;
};

type ResolvedHookInstallation = {
  providerId: string;
  roots: string[];
  isInstalled(): Promise<boolean>;
  install(): Promise<void>;
};

export class AgentHookInstaller {
  private readonly installed = new Set<string>();
  private readonly rootLocks = new Map<string, Promise<void>>();

  constructor(private readonly options: AgentHookInstallerOptions) {}

  async hooksStatus(providerId: string): Promise<HookInstallationStatus | null> {
    const installation = await this.resolveInstallation({ providerId });
    if (!installation) return null;

    let installed = false;
    try {
      installed =
        this.installed.has(this.memoKey(installation)) || (await installation.isInstalled());
      if (installed) this.installed.add(this.memoKey(installation));
    } catch (error) {
      this.options.logger.warn('AgentHookInstaller: failed to inspect hooks', {
        providerId,
        resolvedRoot: installation.roots[0],
        error: String(error),
      });
    }

    return {
      state: installed ? 'installed' : 'pending-install',
      resolvedRoot: installation.roots[0],
    };
  }

  async ensureHooksInstalled(params: {
    providerId: string;
    workspacePath: string;
  }): Promise<boolean> {
    try {
      const installation = await this.resolveInstallation(params);
      if (!installation) return false;

      const memoKey = this.memoKey(installation);
      if (this.installed.has(memoKey)) return true;

      await this.withRootLocks(installation.roots, async () => {
        if (this.installed.has(memoKey)) return;
        if (!(await installation.isInstalled())) await installation.install();
        if (!(await installation.isInstalled())) {
          throw new Error('provider did not report hooks installed after writing config');
        }
        this.installed.add(memoKey);
      });
      return true;
    } catch (error) {
      this.options.logger.warn('AgentHookInstaller: failed to ensure hooks installed', {
        providerId: params.providerId,
        workspacePath: params.workspacePath,
        error: String(error),
      });
      return false;
    }
  }

  private async resolveInstallation(params: {
    providerId: string;
    workspacePath?: string;
  }): Promise<ResolvedHookInstallation | null> {
    const plugin = this.options.agentHost.get(params.providerId);
    const descriptor = plugin?.capabilities.hooks;
    if (!plugin || !descriptor || descriptor.kind === 'none') return null;

    const configContext = await this.options.agentHost.configRootContext();
    if (descriptor.kind === 'config' && plugin.behavior.hooks) {
      const behavior = plugin.behavior.hooks;
      const roots =
        descriptor.scope === 'global'
          ? behavior.resolveConfigRoots(configContext)
          : params.workspacePath
            ? [params.workspacePath]
            : [];
      if (roots.length === 0) return null;
      return {
        providerId: params.providerId,
        roots,
        isInstalled: async () =>
          everyAsync(roots, (root) => behavior.getHooksInstalled(createLocalPluginFs(root))),
        install: async () => {
          for (const root of roots) {
            const fs = createLocalPluginFs(root);
            if (!(await behavior.getHooksInstalled(fs))) {
              await behavior.writeHooks(fs, []);
            }
          }
        },
      };
    }

    if (descriptor.kind === 'plugin' && plugin.behavior.plugins) {
      const behavior = plugin.behavior.plugins;
      const root =
        descriptor.scope === 'global'
          ? behavior.resolveConfigRoot(configContext)
          : params.workspacePath;
      if (!root) return null;
      const scope: PluginScope =
        descriptor.scope === 'global' ? { kind: 'global' } : { kind: 'workspace', path: root };
      const fs = createLocalPluginFs(root);
      return {
        providerId: params.providerId,
        roots: [root],
        isInstalled: () => behavior.isPluginInstalled(fs, scope),
        install: async () => {
          await behavior.installPlugin(fs, scope);
        },
      };
    }

    return null;
  }

  private memoKey(installation: ResolvedHookInstallation): string {
    return `${installation.providerId}\0${installation.roots[0]}`;
  }

  private async withRootLocks<T>(roots: string[], operation: () => Promise<T>): Promise<T> {
    const uniqueRoots = [...new Set(roots)].sort();
    const run = async (index: number): Promise<T> => {
      const root = uniqueRoots[index];
      if (!root) return operation();
      return this.withRootLock(root, () => run(index + 1));
    };
    return run(0);
  }

  private async withRootLock<T>(root: string, operation: () => Promise<T>): Promise<T> {
    const previous = this.rootLocks.get(root) ?? Promise.resolve();
    let release = (): void => {};
    const current = new Promise<void>((resolve) => {
      release = resolve;
    });
    const tail = previous.then(() => current);
    this.rootLocks.set(root, tail);
    await previous;
    try {
      return await operation();
    } finally {
      release();
      if (this.rootLocks.get(root) === tail) this.rootLocks.delete(root);
    }
  }
}

async function everyAsync<T>(
  items: T[],
  predicate: (item: T) => Promise<boolean>
): Promise<boolean> {
  for (const item of items) {
    if (!(await predicate(item))) return false;
  }
  return true;
}
