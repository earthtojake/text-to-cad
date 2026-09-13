import { promises as nodeFs } from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createScope } from '@emdash/shared/concurrency';
import { createStubLogger, deferred } from '@emdash/shared/testing';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { IExecutionContext } from '#primitives/exec/api';
import type { HostDependencyResolver } from '#primitives/host-dependencies/api';
import {
  AgentPluginHost,
  createPluginRegistry,
  type CLIAgentPluginProvider,
  type IHooksBehavior,
  type IPlugins,
} from '#services/agent-plugins/api/plugins';
import { configRoots, envConfigRoot } from '#services/agent-plugins/api/plugins/helpers';
import { AgentHookInstaller } from './hook-installer';

const tempDirs: string[] = [];

afterEach(async () => {
  await Promise.all(
    tempDirs.splice(0).map((dir) => nodeFs.rm(dir, { recursive: true, force: true }))
  );
});

describe('AgentHookInstaller', () => {
  it('uses the allowlisted provider home seen by the spawned CLI and avoids steady-state writes', async () => {
    const homeDir = await makeTempDir();
    const configRoot = path.join(homeDir, 'custom-codex');
    const writeHooks = vi.fn(async (fs) => {
      await fs.write('hooks.json', 'installed');
      return ['hooks.json'];
    });
    const behavior = hookBehavior({
      resolveConfigRoots: configRoots(envConfigRoot('CODEX_HOME', '.codex')),
      writeHooks,
    });
    const installer = createInstaller(homeDir, { CODEX_HOME: configRoot }, [
      hookProvider('codex', behavior),
    ]);

    await expect(
      installer.ensureHooksInstalled({ providerId: 'codex', workspacePath: '/workspace' })
    ).resolves.toBe(true);
    await expect(
      installer.ensureHooksInstalled({ providerId: 'codex', workspacePath: '/other-workspace' })
    ).resolves.toBe(true);

    expect(writeHooks).toHaveBeenCalledTimes(1);
    await expect(nodeFs.readFile(path.join(configRoot, 'hooks.json'), 'utf8')).resolves.toBe(
      'installed'
    );
  });

  it('serializes writes shared by providers resolving to the same root', async () => {
    const homeDir = await makeTempDir();
    const root = path.join(homeDir, '.shared');
    const firstStarted = deferred<void>();
    const releaseFirst = deferred<void>();
    let activeWrites = 0;
    let maxActiveWrites = 0;
    const makeBehavior = (file: string): IHooksBehavior =>
      hookBehavior({
        resolveConfigRoots: () => [root],
        getHooksInstalled: async (fs) => fs.exists(file),
        writeHooks: async (fs) => {
          activeWrites += 1;
          maxActiveWrites = Math.max(maxActiveWrites, activeWrites);
          if (file === 'a.json') {
            firstStarted.resolve();
            await releaseFirst.promise;
          }
          await fs.write(file, 'installed');
          activeWrites -= 1;
          return [file];
        },
      });
    const installer = createInstaller(homeDir, {}, [
      hookProvider('a', makeBehavior('a.json')),
      hookProvider('b', makeBehavior('b.json')),
    ]);

    const first = installer.ensureHooksInstalled({ providerId: 'a', workspacePath: '/workspace' });
    await firstStarted.promise;
    const second = installer.ensureHooksInstalled({ providerId: 'b', workspacePath: '/workspace' });
    await Promise.resolve();
    expect(maxActiveWrites).toBe(1);

    releaseFirst.resolve();
    await Promise.all([first, second]);
    expect(maxActiveWrites).toBe(1);
  });

  it('installs file-drop plugins relative to their resolved global root', async () => {
    const homeDir = await makeTempDir();
    const configRoot = path.join(homeDir, 'plugin-home');
    const pluginPath = 'plugins/emdash.ts';
    const behavior: IPlugins = {
      resolveConfigRoot: envConfigRoot('OPENCODE_CONFIG_DIR', '.test-plugin'),
      installPlugin: async (fs) => {
        await fs.write(pluginPath, 'installed');
        return [pluginPath];
      },
      uninstallPlugin: async (fs) => fs.delete(pluginPath),
      isPluginInstalled: async (fs) => fs.exists(pluginPath),
      getPluginVersion: async () => '1',
      getPluginPath: async () => pluginPath,
    };
    const installer = createInstaller(homeDir, { OPENCODE_CONFIG_DIR: configRoot }, [
      pluginProvider('plugin-agent', behavior),
    ]);

    await expect(
      installer.ensureHooksInstalled({ providerId: 'plugin-agent', workspacePath: '/workspace' })
    ).resolves.toBe(true);
    await expect(nodeFs.readFile(path.join(configRoot, pluginPath), 'utf8')).resolves.toBe(
      'installed'
    );
  });
});

function hookBehavior(overrides: Partial<IHooksBehavior>): IHooksBehavior {
  return {
    resolveConfigRoots: () => ['/tmp/test-hooks'],
    readHooks: async () => [],
    writeHooks: async () => [],
    deleteHooks: async () => {},
    getHooksInstalled: async (fs) => fs.exists('hooks.json'),
    ...overrides,
  };
}

function hookProvider(id: string, behavior: IHooksBehavior): CLIAgentPluginProvider {
  return {
    metadata: { id, name: id, description: id, websiteUrl: 'https://example.com' },
    capabilities: {
      hooks: { kind: 'config', scope: 'global', supportedEvents: ['start'] },
      prompt: { kind: 'argv' },
      hostDependency: { id, binaryNames: [id] },
    },
    behavior: { hooks: behavior },
  } as unknown as CLIAgentPluginProvider;
}

function pluginProvider(id: string, behavior: IPlugins): CLIAgentPluginProvider {
  return {
    metadata: { id, name: id, description: id, websiteUrl: 'https://example.com' },
    capabilities: {
      hooks: { kind: 'plugin', scope: 'global', supportedEvents: ['start'] },
      plugins: { kind: 'file-drop', scope: 'global' },
      prompt: { kind: 'argv' },
      hostDependency: { id, binaryNames: [id] },
    },
    behavior: { plugins: behavior },
  } as unknown as CLIAgentPluginProvider;
}

function createInstaller(
  homeDir: string,
  env: Record<string, string>,
  plugins: CLIAgentPluginProvider[]
): AgentHookInstaller {
  const registry = createPluginRegistry<CLIAgentPluginProvider>();
  for (const plugin of plugins) registry.register(plugin);
  const agentHost = new AgentPluginHost({
    scope: createScope({ label: 'hook-installer-test' }),
    registry,
    exec: fakeExec(),
    dependencies: fakeDependencies(),
    fs: {
      read: async () => null,
      write: async () => {},
      delete: async () => {},
      exists: async () => false,
      list: async () => [],
    },
    env: async () => ({ HOME: homeDir, PATH: '/bin', ...env }),
    homeDir,
    platform: 'linux',
  });
  const { logger } = createStubLogger();
  return new AgentHookInstaller({ agentHost, logger });
}

async function makeTempDir(): Promise<string> {
  const dir = await nodeFs.mkdtemp(path.join(os.tmpdir(), 'emdash-hooks-'));
  tempDirs.push(dir);
  return dir;
}

function fakeDependencies(): HostDependencyResolver {
  return {
    resolve: async (id) => ({
      success: true,
      data: { id, command: id, path: id, realpath: id, source: { kind: 'auto' } },
    }),
  };
}

function fakeExec(): IExecutionContext {
  return {
    supportsLocalSpawn: false,
    exec: async () => ({ stdout: '', stderr: '' }),
    execStreaming: async () => ({ exitCode: 0 }),
    dispose() {},
  };
}
