import { randomUUID } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import type { HostAbsolutePath } from '@emdash/core/primitives/path/api';
import { err, ok } from '@emdash/shared';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { nativePathFromHost } from '@core/primitives/desktop-runtime/api';
import type { RepoFacts } from '@core/primitives/project-settings/api';
import { filesClientScope } from '@core/services/runtime-broker/node/files';
import type { ProjectSettingsStorage, StoredProjectSettings } from './project-settings-storage';
import { HostProjectSettingsProvider } from './providers/host-project-settings-provider';

/**
 * Provider-level coverage for the lazy read-path settings migrations
 * (spec: github-git-settings §10) against row fixtures.
 */

const REPO_FACTS: RepoFacts = {
  remotes: [
    { name: 'origin', host: 'github.com', headBranch: 'main', branches: ['main', 'develop'] },
    { name: 'upstream', host: 'github.com', headBranch: 'main', branches: ['main'] },
  ],
  localBranches: ['main', 'feature/x'],
};

function makeConfigFiles(projectPath: string) {
  const client = {
    fs: {
      exists: vi.fn(async ({ path: target }: { path: HostAbsolutePath }) =>
        ok({ exists: fs.existsSync(nativePathFromHost(target)) })
      ),
      readText: vi.fn(async ({ path: target }: { path: HostAbsolutePath }) => {
        try {
          const content = fs.readFileSync(nativePathFromHost(target), 'utf8');
          return ok({
            content,
            truncated: false,
            totalSize: Buffer.byteLength(content),
            etag: 'test-etag',
          });
        } catch {
          return err({ type: 'not-found' as const, path: nativePathFromHost(target) });
        }
      }),
    },
  };
  return filesClientScope(client as never, projectPath);
}

function makeRowStorage(initialBaseJson?: string) {
  const rows = new Map<string, StoredProjectSettings>();
  const seededRow = initialBaseJson
    ? {
        baseProjectSettingsJson: initialBaseJson,
        shareableProjectSettingsJson: '{}',
        legacyConfigMigratedAt: new Date().toISOString(),
      }
    : undefined;
  const storage: ProjectSettingsStorage = {
    get: async (projectId) => rows.get(projectId) ?? seededRowFor(projectId),
    insertIfMissing: async (projectId, settings) => {
      if (!rows.has(projectId) && !seededRow) rows.set(projectId, settings);
    },
    update: async (projectId, settings) => {
      const current = rows.get(projectId) ?? seededRowFor(projectId);
      rows.set(projectId, { ...current!, ...settings });
    },
  };
  function seededRowFor(projectId: string): StoredProjectSettings | undefined {
    if (!seededRow) return undefined;
    if (!rows.has(projectId)) rows.set(projectId, { ...seededRow });
    return rows.get(projectId);
  }
  return {
    storage,
    baseJson: (projectId: string) => JSON.parse(rows.get(projectId)!.baseProjectSettingsJson),
  };
}

const tempDirs: string[] = [];

afterEach(() => {
  for (const dir of tempDirs.splice(0)) {
    fs.rmSync(dir, { recursive: true, force: true });
  }
});

function makeProvider(options: {
  baseJson?: string;
  storage?: ProjectSettingsStorage;
  getRepoFacts?: () => Promise<RepoFacts | null>;
  defaultBranchFallback?: string;
  hostTmux?: boolean | null | (() => boolean | null);
  appDefaultTmux?: boolean;
}) {
  const projectPath = fs.mkdtempSync(path.join(os.tmpdir(), 'emdash-lazy-migrations-'));
  tempDirs.push(projectPath);
  const projectId = `project-${randomUUID()}`;
  const rowStorage = options.storage ? undefined : makeRowStorage(options.baseJson);
  const provider = new HostProjectSettingsProvider(
    projectId,
    projectPath,
    options.defaultBranchFallback ?? 'origin/main',
    makeConfigFiles(projectPath),
    {
      placementContext: () =>
        Promise.resolve({
          hostWorktreeRoot: '/tmp/emdash/worktrees',
          builtInWorktreeRoot: '/tmp/emdash/worktrees',
          homeDirectory: '/tmp',
          hostTmux:
            typeof options.hostTmux === 'function'
              ? options.hostTmux()
              : (options.hostTmux ?? null),
          appDefaultTmux: options.appDefaultTmux ?? false,
        }),
      storage: options.storage ?? rowStorage!.storage,
      getRepoFacts: options.getRepoFacts,
      worktreeDirectoryFileSystem: {
        mkdir: async () => ok(),
        realPath: async (targetPath) => ok(targetPath),
      },
    }
  );
  return { provider, projectId, rowStorage };
}

describe('lazy settings migrations in the provider', () => {
  it('keeps partial legacy lifecycle values retryable while exposing only current settings', async () => {
    const row: StoredProjectSettings = {
      baseProjectSettingsJson: JSON.stringify({
        worktreeDirectory: '/tmp/legacy-worktrees',
        autoRunSetupScriptOnTaskCreation: false,
      }),
      shareableProjectSettingsJson: JSON.stringify({
        preservePatterns: [],
      }),
      legacyConfigMigratedAt: new Date().toISOString(),
    };
    const update = vi.fn(async (_projectId: string, patch: Partial<StoredProjectSettings>) => {
      Object.assign(row, patch);
    });
    const storage: ProjectSettingsStorage = {
      get: async () => row,
      insertIfMissing: vi.fn(),
      update,
    };
    const { provider } = makeProvider({ storage });

    await expect(provider.getStoredGitSettings()).resolves.toEqual({
      worktreeRoot: '/tmp/legacy-worktrees',
    });
    expect(JSON.parse(row.baseProjectSettingsJson)).toEqual({
      worktreeRoot: '/tmp/legacy-worktrees',
      tmuxDefaultMigrated: true,
      autoRunSetupScriptOnTaskCreation: false,
    });
    expect(update).toHaveBeenCalledOnce();
    await expect(provider.readLegacyLifecycleSettings()).resolves.toEqual({
      preservePatterns: [],
      autoRunSetup: false,
    });
  });

  it('reads a row with all legacy forms back in the new model and rewrites it', async () => {
    const { provider, projectId, rowStorage } = makeProvider({
      baseJson: JSON.stringify({
        defaultBranch: 'origin/main',
        baseRemote: 'origin',
        githubAccountId: 'github.com:42',
        worktreeDirectory: '/tmp/legacy-worktrees',
        tmux: true,
      }),
      getRepoFacts: async () => REPO_FACTS,
    });

    await expect(provider.getStoredPlacementSettings()).resolves.toEqual({ tmux: true });

    // The row is physically rewritten: seeded values cleared (they match the
    // inference), legacy keys renamed and restructured.
    expect(rowStorage!.baseJson(projectId)).toEqual({
      githubAccount: { kind: 'account', accountId: 'github.com:42' },
      worktreeRoot: '/tmp/legacy-worktrees',
      tmux: true,
      tmuxDefaultMigrated: true,
    });

    // The stored-model surface exposes only explicit choices.
    await expect(provider.getStoredGitSettings()).resolves.toEqual({
      githubAccount: { kind: 'account', accountId: 'github.com:42' },
      worktreeRoot: '/tmp/legacy-worktrees',
    });
  });

  it('demotes values matching inference and keeps divergent values pinned', async () => {
    const { provider, projectId, rowStorage } = makeProvider({
      baseJson: JSON.stringify({
        defaultBranch: 'origin/develop',
        baseRemote: 'origin',
      }),
      getRepoFacts: async () => REPO_FACTS,
    });

    await provider.getStoredGitSettings();

    // baseRemote 'origin' matches inference and is cleared; the divergent
    // defaultBranch survives as an explicit (structured) setting.
    expect(rowStorage!.baseJson(projectId)).toEqual({
      defaultBranch: { remote: 'origin', branch: 'develop' },
      tmuxDefaultMigrated: true,
    });
    await expect(provider.getStoredGitSettings()).resolves.toEqual({
      defaultBranch: { remote: 'origin', branch: 'develop' },
    });
  });

  it('keeps stored values pinned when repo facts are unavailable and retries next read', async () => {
    let factsAvailable = false;
    const { provider, projectId, rowStorage } = makeProvider({
      baseJson: JSON.stringify({
        defaultBranch: { remote: 'origin', branch: 'main' },
        baseRemote: 'origin',
      }),
      getRepoFacts: async () => (factsAvailable ? REPO_FACTS : null),
    });

    await provider.getStoredGitSettings();
    // No destructive migration without facts: both values survive.
    expect(rowStorage!.baseJson(projectId)).toEqual({
      defaultBranch: { remote: 'origin', branch: 'main' },
      baseRemote: 'origin',
      tmuxDefaultMigrated: true,
    });

    factsAvailable = true;
    await provider.getStoredGitSettings();
    // The next read demotes both values (they match the inference).
    expect(rowStorage!.baseJson(projectId)).toEqual({ tmuxDefaultMigrated: true });
  });

  it('reads legacy null account rows back as absent (infer)', async () => {
    const { provider, projectId, rowStorage } = makeProvider({
      baseJson: JSON.stringify({ githubAccountId: null, tmux: true }),
    });

    await expect(provider.getStoredGitSettings()).resolves.toEqual({});
    expect(rowStorage!.baseJson(projectId)).toEqual({
      tmux: true,
      tmuxDefaultMigrated: true,
    });
    await expect(provider.getStoredGitSettings()).resolves.toEqual({});
  });

  it('keeps an explicit stored none distinct from absent', async () => {
    const { provider } = makeProvider({
      baseJson: JSON.stringify({ githubAccount: { kind: 'none' } }),
    });

    await expect(provider.getStoredGitSettings()).resolves.toEqual({
      githubAccount: { kind: 'none' },
    });
  });

  it('creates new projects without seeding project-level defaults', async () => {
    const { provider, projectId, rowStorage } = makeProvider({});

    await expect(provider.getStoredGitSettings()).resolves.toEqual({});
    await expect(provider.getStoredPlacementSettings()).resolves.toEqual({});
    expect(rowStorage!.baseJson(projectId)).toEqual({ tmuxDefaultMigrated: true });
    await expect(provider.resolveTmux()).resolves.toEqual({
      value: false,
      provenance: { kind: 'inferred', from: 'app default' },
    });
  });

  it('follows host tmux changes until set and resumes inheritance after reset', async () => {
    let hostTmux = false;
    const { provider } = makeProvider({ hostTmux: () => hostTmux });

    await expect(provider.resolveTmux()).resolves.toEqual({
      value: false,
      provenance: { kind: 'inferred', from: 'host default' },
    });

    hostTmux = true;
    await expect(provider.resolveTmux()).resolves.toEqual({
      value: true,
      provenance: { kind: 'inferred', from: 'host default' },
    });

    await expect(provider.patch({ placement: { stored: { tmux: false } } })).resolves.toMatchObject(
      { success: true }
    );
    await expect(provider.resolveTmux()).resolves.toEqual({
      value: false,
      provenance: { kind: 'set' },
    });

    await expect(provider.patch({ placement: { stored: { tmux: null } } })).resolves.toMatchObject({
      success: true,
    });
    await expect(provider.resolveTmux()).resolves.toEqual({
      value: true,
      provenance: { kind: 'inferred', from: 'host default' },
    });
  });

  it('demotes a materialized tmux default once and preserves later explicit choices', async () => {
    const { provider, projectId, rowStorage } = makeProvider({
      baseJson: JSON.stringify({ tmux: true }),
      hostTmux: true,
    });

    await expect(provider.getStoredPlacementSettings()).resolves.toEqual({});
    expect(rowStorage!.baseJson(projectId)).toEqual({ tmuxDefaultMigrated: true });

    await expect(provider.patch({ placement: { stored: { tmux: true } } })).resolves.toMatchObject({
      success: true,
    });
    await expect(provider.getStoredPlacementSettings()).resolves.toEqual({ tmux: true });
    expect(rowStorage!.baseJson(projectId)).toEqual({
      tmux: true,
      tmuxDefaultMigrated: true,
    });
  });

  it('keeps a stored tmux value that differs from the current inherited default', async () => {
    const { provider, projectId, rowStorage } = makeProvider({
      baseJson: JSON.stringify({ tmux: false }),
      hostTmux: true,
    });

    await expect(provider.getStoredPlacementSettings()).resolves.toEqual({ tmux: false });
    expect(rowStorage!.baseJson(projectId)).toEqual({
      tmux: false,
      tmuxDefaultMigrated: true,
    });
  });

  it('follows host-default changes until a project override is set, then inherits again on reset', async () => {
    const options = { hostTmux: false as boolean | null };
    const { provider } = makeProvider(options);

    await expect(provider.resolveTmux()).resolves.toEqual({
      value: false,
      provenance: { kind: 'inferred', from: 'host default' },
    });
    options.hostTmux = true;
    await expect(provider.resolveTmux()).resolves.toEqual({
      value: true,
      provenance: { kind: 'inferred', from: 'host default' },
    });

    await provider.patch({ placement: { stored: { tmux: false } } });
    await expect(provider.resolveTmux()).resolves.toEqual({
      value: false,
      provenance: { kind: 'set' },
    });

    await provider.patch({ placement: { stored: { tmux: null } } });
    await expect(provider.resolveTmux()).resolves.toEqual({
      value: true,
      provenance: { kind: 'inferred', from: 'host default' },
    });
  });

  it('persists updates in the stored model', async () => {
    const { provider, projectId, rowStorage } = makeProvider({
      getRepoFacts: async () => REPO_FACTS,
    });

    const result = await provider.patch({
      gitIdentity: {
        stored: {
          defaultBranch: { remote: 'origin', branch: 'develop' },
          baseRemote: 'upstream',
          githubAccount: { kind: 'account', accountId: 'github.com:42' },
        },
      },
      placement: { stored: { worktreeRoot: '/tmp/updated-worktrees' } },
    });
    expect(result.success).toBe(true);

    expect(rowStorage!.baseJson(projectId)).toEqual({
      defaultBranch: { remote: 'origin', branch: 'develop' },
      baseRemote: 'upstream',
      githubAccount: { kind: 'account', accountId: 'github.com:42' },
      worktreeRoot: '/tmp/updated-worktrees',
      tmuxDefaultMigrated: true,
    });
    await expect(provider.getStoredGitSettings()).resolves.toEqual({
      defaultBranch: { remote: 'origin', branch: 'develop' },
      baseRemote: 'upstream',
      githubAccount: { kind: 'account', accountId: 'github.com:42' },
      worktreeRoot: '/tmp/updated-worktrees',
    });
  });
});
