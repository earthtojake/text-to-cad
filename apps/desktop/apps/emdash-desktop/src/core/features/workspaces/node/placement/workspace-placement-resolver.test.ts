import path from 'node:path';
import { hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import { err, ok } from '@emdash/shared';
import { describe, expect, it, vi } from 'vitest';
import { WorkspacePlacementResolver } from '@core/features/workspaces/api/node/placement/workspace-placement-resolver';
import { hostPathFromNative, nativePathFromHost } from '@core/primitives/desktop-runtime/api';
import type { LocalProject } from '@core/primitives/projects/api';

const project: LocalProject = {
  type: 'local',
  id: 'project-1',
  name: 'Emdash',
  path: '/home/jona/emdash/repositories/emdash',
  baseRef: 'main',
  repositoryWorkspaceId: null,
  createdAt: '2026-01-01',
  updatedAt: '2026-01-01',
};

function makeResolver(options: {
  home?: string;
  existingPaths?: string[];
  registeredPaths?: string[];
  missingParents?: string[];
  appOverrides?: Record<string, string>;
  projectOverride?: string;
  hostWorktreeRoot?: string;
  homeError?: Error;
}) {
  const existingPaths = new Set(options.existingPaths ?? []);
  const registeredPaths = new Set(options.registeredPaths ?? []);
  const missingParents = new Set(options.missingParents ?? []);
  const getHomeDir = vi.fn(async () => {
    if (options.homeError) throw options.homeError;
    return { path: hostPathFromNative(options.home ?? '/home/jona') };
  });
  const exists = vi.fn(async ({ path: target }) => {
    const candidate = nativePathFromHost(target);
    if (missingParents.has(path.posix.dirname(candidate))) {
      return err({ type: 'not-found' as const, path: '' });
    }
    return ok({ exists: existingPaths.has(candidate) });
  });
  const hostSettings = {
    get: vi.fn(async () =>
      ok({
        settings: options.hostWorktreeRoot ? { worktreeRoot: options.hostWorktreeRoot } : {},
        parseError: false,
      })
    ),
  };
  const broker = {
    client: vi.fn(async () => ok({ files: { getHomeDir, fs: { exists } }, hostSettings })),
  };
  const resolver = new WorkspacePlacementResolver({
    broker: broker as never,
    getSettings: () => ({
      getWithMeta: vi.fn(async () => ({
        value: {},
        defaults: {},
        overrides: options.appOverrides ?? {},
      })) as never,
    }),
    findProjectByPath: vi.fn(async (_host, candidate) =>
      registeredPaths.has(candidate) ? project : undefined
    ),
    getStoredProjectWorktreeRoot: vi.fn(async () => options.projectOverride),
  });
  return { resolver, broker, exists, getHomeDir };
}

describe('WorkspacePlacementResolver', () => {
  it('resolves the default repositories root on the target host', async () => {
    const { resolver } = makeResolver({ home: '/home/remote' });

    await expect(resolver.resolveRepositoriesRoot(hostRef('remote', 'ssh-1'))).resolves.toEqual({
      success: true,
      data: '/home/remote/hardcore/repositories',
    });
  });

  it('expands the configured repositories root against the target host home', async () => {
    const { resolver } = makeResolver({
      home: '/home/remote',
      appOverrides: { defaultProjectsDirectory: '~/source' },
    });

    await expect(resolver.resolveRepositoriesRoot(hostRef('remote', 'ssh-1'))).resolves.toEqual({
      success: true,
      data: '/home/remote/source',
    });
  });

  it('propagates host-home failures while resolving the repositories root', async () => {
    const { resolver } = makeResolver({ homeError: new Error('home unavailable') });

    await expect(resolver.resolveRepositoriesRoot(LOCAL_HOST_REF)).resolves.toEqual({
      success: false,
      error: { type: 'host-home-unavailable', message: 'home unavailable' },
    });
  });

  it('derives the project pool from the target host default', async () => {
    const { resolver, getHomeDir } = makeResolver({ home: '/home/jona' });

    await expect(resolver.resolveWorktreePool(project)).resolves.toEqual({
      success: true,
      data: '/home/jona/hardcore/worktrees/emdash-ba5cbeaf',
    });
    await resolver.resolveWorktreePool(project);
    expect(getHomeDir).toHaveBeenCalledTimes(1);
  });

  it('expands a per-project override against the target host home', async () => {
    const { resolver } = makeResolver({
      home: '/home/remote',
      projectOverride: '~/fast-worktrees',
    });

    const remoteProject = {
      ...project,
      type: 'ssh' as const,
      connectionId: 'ssh-1',
      path: '/srv/repositories/emdash',
    };
    const result = await resolver.resolveWorktreePool(remoteProject);

    expect(result).toMatchObject({
      success: true,
      data: expect.stringMatching(/^\/home\/remote\/fast-worktrees\/emdash-[a-f0-9]{8}$/u),
    });
  });

  it('uses the host-settings worktree root when the project has no override', async () => {
    const { resolver } = makeResolver({
      home: '/home/jona',
      hostWorktreeRoot: '~/host-worktrees',
    });

    const result = await resolver.resolveWorktreePool(project);

    expect(result).toMatchObject({
      success: true,
      data: expect.stringMatching(/^\/home\/jona\/host-worktrees\/emdash-[a-f0-9]{8}$/u),
    });
  });

  it('prefers the per-project override over the host-settings worktree root', async () => {
    const { resolver } = makeResolver({
      home: '/home/jona',
      hostWorktreeRoot: '~/host-worktrees',
      projectOverride: '~/project-worktrees',
    });

    const result = await resolver.resolveWorktreePool(project);

    expect(result).toMatchObject({
      success: true,
      data: expect.stringMatching(/^\/home\/jona\/project-worktrees\/emdash-[a-f0-9]{8}$/u),
    });
  });

  it('degrades an unusable project override to the host worktree root', async () => {
    const { resolver } = makeResolver({
      home: '/home/jona',
      hostWorktreeRoot: '~/host-worktrees',
      projectOverride: 'relative/never-works',
    });

    const result = await resolver.resolveWorktreePool(project);

    expect(result).toMatchObject({
      success: true,
      data: expect.stringMatching(/^\/home\/jona\/host-worktrees\/emdash-[a-f0-9]{8}$/u),
    });
  });

  it('degrades unusable project and host roots to the built-in root', async () => {
    const { resolver } = makeResolver({
      home: '/home/jona',
      hostWorktreeRoot: 'also-relative',
      projectOverride: 'relative/never-works',
    });

    const result = await resolver.resolveWorktreePool(project);

    expect(result).toMatchObject({
      success: true,
      data: expect.stringMatching(/^\/home\/jona\/hardcore\/worktrees\/emdash-[a-f0-9]{8}$/u),
    });
  });

  it('resolves a new path under an existing parent', async () => {
    const { resolver, exists } = makeResolver({ home: '/home/jona' });

    await expect(
      resolver.resolveRepositoryDestination(LOCAL_HOST_REF, 'emdash', '/chosen')
    ).resolves.toEqual({ success: true, data: '/chosen/emdash' });
    expect(exists).toHaveBeenCalledWith(
      expect.objectContaining({ path: hostPathFromNative('/chosen/emdash') })
    );
  });

  it('treats a missing parent directory as an available candidate', async () => {
    const { resolver } = makeResolver({
      home: '/home/jona',
      missingParents: ['/home/jona/hardcore/repositories'],
    });

    await expect(resolver.resolveRepositoryDestination(LOCAL_HOST_REF, 'api')).resolves.toEqual({
      success: true,
      data: '/home/jona/hardcore/repositories/api',
    });
  });

  it('suffixes clone destinations occupied in either the filesystem or project registry', async () => {
    const { resolver } = makeResolver({
      home: '/home/jona',
      existingPaths: ['/chosen/emdash'],
      registeredPaths: ['/chosen/emdash-2'],
    });

    await expect(
      resolver.resolveRepositoryDestination(LOCAL_HOST_REF, 'emdash', '/chosen')
    ).resolves.toEqual({ success: true, data: '/chosen/emdash-3' });
  });

  it('uses an explicit app root on the target host when the UI does not choose one', async () => {
    const { resolver } = makeResolver({
      appOverrides: { defaultProjectsDirectory: '~/source' },
    });

    await expect(
      resolver.resolveRepositoryDestination(hostRef('remote', 'ssh-1'), 'api')
    ).resolves.toEqual({ success: true, data: '/home/jona/source/api' });
  });

  it('returns runtime and filesystem failures without allocating a path', async () => {
    const runtimeFailure = {
      type: 'runtime-host-unavailable' as const,
      host: LOCAL_HOST_REF,
      message: 'offline',
    };
    const resolver = new WorkspacePlacementResolver({
      broker: {
        client: async () => err(runtimeFailure),
      } as never,
      getSettings: () => ({ getWithMeta: vi.fn() }) as never,
      findProjectByPath: vi.fn(),
      getStoredProjectWorktreeRoot: vi.fn(),
    });

    await expect(resolver.resolveRepositoryDestination(LOCAL_HOST_REF, 'repo')).resolves.toEqual(
      err(runtimeFailure)
    );
  });
});
