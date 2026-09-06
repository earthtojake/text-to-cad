import path from 'node:path';
import { hostRefKey, type HostRef } from '@emdash/core/primitives/host/api';
import { type HostAbsolutePath } from '@emdash/core/primitives/path/api';
import type {
  HostRuntimesClient,
  RuntimeResolveError,
} from '@emdash/core/services/runtime-broker/api';
import { err, ok, type Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import {
  fileKeyForAbsolutePath,
  hostPathFromNative,
  nativePathFromHost,
} from '@core/primitives/desktop-runtime/api';
import { safePathSegment } from '@core/primitives/path-name/api';
import { builtInWorktreeRootFor, resolveWorktreeRoot } from '@core/primitives/project-settings/api';
import {
  projectHostRef,
  type Project,
  type ProjectPlacementError,
} from '@core/primitives/projects/api';
import { hostSettingsDefaults } from '@core/services/runtime-broker/node/host-settings';
import type { AppSettingsService } from '@core/services/settings/node';
import { defaultRepositoriesRoot, deriveWorktreePoolPath } from './placement-defaults';

export type WorkspacePlacementError = ProjectPlacementError;

type RuntimeBrokerLike = {
  client(host: HostRef): Promise<Result<HostRuntimesClient, RuntimeResolveError>>;
};

type PlacementResolverDependencies = {
  broker: RuntimeBrokerLike;
  getSettings: () => Pick<AppSettingsService, 'getWithMeta'>;
  findProjectByPath(host: HostRef, path: string): Promise<Project | undefined>;
  /**
   * The stored per-project worktree-root override, from the one settings
   * provider model (spec: github-git-settings §6): the mounted provider's
   * `getStoredGitSettings()` when the project is open, the shared row reader
   * (`loadStoredGitSettings`) before it mounts. Never a raw-JSON side read.
   */
  getStoredProjectWorktreeRoot: (projectId: string) => Promise<string | undefined>;
};

export class WorkspacePlacementResolver {
  private readonly homeDirectories = new Map<
    string,
    Promise<Result<string, WorkspacePlacementError>>
  >();

  constructor(private readonly dependencies: PlacementResolverDependencies) {}

  async resolveWorktreeRoot(project: Project): Promise<Result<string, WorkspacePlacementError>> {
    const host = projectHostRef(project);
    const homeResult = await this.getHomeDirectory(host);
    if (!homeResult.success) return homeResult;

    // The blessed worktree-root chain (spec: github-git-settings §6):
    // per-project override → per-host default → built-in root, resolved by the
    // same portable function the settings page and create-task preview use.
    // Invalid configured roots degrade inside the chain with a warning here —
    // placement is never blocked by a stale root setting.
    const [projectWorktreeRoot, hostWorktreeRoot] = await Promise.all([
      this.dependencies.getStoredProjectWorktreeRoot(project.id),
      this.getHostWorktreeRoot(host),
    ]);
    const resolved = resolveWorktreeRoot({
      projectWorktreeRoot,
      hostWorktreeRoot: hostWorktreeRoot ?? null,
      builtInWorktreeRoot: builtInWorktreeRootFor(homeResult.data),
      homeDirectory: homeResult.data,
    });
    if (resolved.provenance.kind === 'broken-setting') {
      log.warn('Configured worktree root is unusable; degrading to the next layer', {
        projectId: project.id,
        staleValue: resolved.provenance.staleValue,
        fallback: resolved.value,
      });
    }
    return ok(resolved.value);
  }

  async resolveWorktreePool(project: Project): Promise<Result<string, WorkspacePlacementError>> {
    const rootResult = await this.resolveWorktreeRoot(project);
    if (!rootResult.success) return rootResult;
    return ok(
      deriveWorktreePoolPath({
        worktreesRoot: rootResult.data,
        repoPath: project.path,
      })
    );
  }

  async resolveRepositoriesRoot(host: HostRef): Promise<Result<string, WorkspacePlacementError>> {
    const homeResult = await this.getHomeDirectory(host);
    if (!homeResult.success) return homeResult;

    const configuredRoot = await this.getExplicitAppRoot('defaultProjectsDirectory');
    return configuredRoot
      ? resolveConfiguredRoot(configuredRoot, homeResult.data)
      : ok(defaultRepositoriesRoot(homeResult.data));
  }

  async resolveRepositoryDestination(
    host: HostRef,
    name: string,
    chosenDir?: string
  ): Promise<Result<string, WorkspacePlacementError>> {
    let rootResult: Result<string, WorkspacePlacementError>;
    if (chosenDir?.trim()) {
      const homeResult = await this.getHomeDirectory(host);
      if (!homeResult.success) return homeResult;
      rootResult = resolveConfiguredRoot(chosenDir, homeResult.data);
    } else {
      rootResult = await this.resolveRepositoriesRoot(host);
    }
    if (!rootResult.success) return rootResult;

    const session = await this.dependencies.broker.client(host);
    if (!session.success) return session;

    const pathApi = pathApiFor(rootResult.data);
    const baseName = safePathSegment(name, 'repository');
    for (let suffix = 1; ; suffix += 1) {
      const candidateName = suffix === 1 ? baseName : `${baseName}-${suffix}`;
      const candidate = pathApi.join(rootResult.data, candidateName);
      const [exists, registeredProject] = await Promise.all([
        session.data.files.fs.exists(fileKeyForAbsolutePath(hostPathFromNative(candidate))),
        this.dependencies.findProjectByPath(host, candidate),
      ]);
      if (!exists.success) {
        if (exists.error.type === 'not-found') {
          if (!registeredProject) return ok(candidate);
          continue;
        }
        return err({
          type: 'filesystem-unavailable',
          path: candidate,
          message: fsErrorMessage(exists.error),
        });
      }
      if (!exists.data.exists && !registeredProject) return ok(candidate);
    }
  }

  clearHostCache(host?: HostRef): void {
    if (host) {
      this.homeDirectories.delete(hostRefKey(host));
      return;
    }
    this.homeDirectories.clear();
  }

  private getHomeDirectory(host: HostRef): Promise<Result<string, WorkspacePlacementError>> {
    const key = hostRefKey(host);
    const cached = this.homeDirectories.get(key);
    if (cached) return cached;

    const pending = this.queryHomeDirectory(host);
    this.homeDirectories.set(key, pending);
    return pending;
  }

  private async queryHomeDirectory(
    host: HostRef
  ): Promise<Result<string, WorkspacePlacementError>> {
    const session = await this.dependencies.broker.client(host);
    if (!session.success) return session;
    try {
      return ok(nativePathFromHost((await session.data.files.getHomeDir()).path));
    } catch (error) {
      return err({
        type: 'host-home-unavailable',
        message: error instanceof Error ? error.message : String(error),
      });
    }
  }

  private async getHostWorktreeRoot(host: HostRef): Promise<string | undefined> {
    const session = await this.dependencies.broker.client(host);
    if (!session.success) return undefined;
    return (await hostSettingsDefaults(session.data.hostSettings)).worktreeRoot;
  }

  private async getExplicitAppRoot(field: 'defaultProjectsDirectory'): Promise<string | undefined> {
    const { overrides } = await this.dependencies.getSettings().getWithMeta('localProject');
    return Object.hasOwn(overrides, field) ? overrides[field] : undefined;
  }
}

function resolveConfiguredRoot(
  configuredRoot: string,
  homeDirectory: string
): Result<string, WorkspacePlacementError> {
  const trimmed = configuredRoot.trim();
  const pathApi = pathApiFor(homeDirectory);
  const expanded =
    trimmed === '~'
      ? homeDirectory
      : trimmed.startsWith('~/') || trimmed.startsWith('~\\')
        ? pathApi.join(homeDirectory, trimmed.slice(2))
        : trimmed;

  if (!pathApi.isAbsolute(expanded)) {
    return err({
      type: 'invalid-host-path',
      path: configuredRoot,
      message: 'Placement roots must be absolute paths on the target host',
    });
  }
  return ok(pathApi.normalize(expanded));
}

function pathApiFor(absolutePath: string): typeof path.posix {
  return /^[a-zA-Z]:[\\/]/u.test(absolutePath) || absolutePath.startsWith('\\\\')
    ? path.win32
    : path.posix;
}

function fsErrorMessage(error: { type: string; message?: string; path?: string }): string {
  return error.message ?? `${error.type}: ${error.path ?? 'unknown path'}`;
}

export const __workspacePlacementTestUtils = {
  resolveConfiguredRoot,
  projectHostRef,
  asHostPath: (path: HostAbsolutePath) => nativePathFromHost(path),
};
