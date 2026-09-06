import type { ProjectConfigState } from '@emdash/core/runtimes/workspace-registry/api';
import { err, ok, type Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import { systemClock, type Clock } from '@emdash/shared/scheduling';
import type { LiveSource } from '@emdash/wire/rpc';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import type { ProjectProvider } from '@core/features/projects/api/node/project-provider';
import { projectEvents } from '@core/features/projects/node';
import type { WorkspaceIdentityService } from '@core/features/workspaces/api/node/workspace-identity-service';
import { HookCore, type Hookable } from '@core/primitives/hooks/api/hookable';
import {
  type MigrateProjectConfigRequest,
  type PlacementContext,
  type ProjectSettingsWriteTargetOption,
  type WriteProjectConfigRequest,
} from '@core/primitives/project-settings/api';
import {
  hasConfiguredShareableProjectSettings,
  resolveTmux,
  resolveWorktreeRoot,
  tombstonePatchFor,
} from '@core/primitives/project-settings/api';
import type { UpdateProjectSettingsError } from '@core/primitives/projects/api';
import type { Project } from '@core/primitives/projects/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { getProjectById } from '../../../node/operations/getProjects';
import {
  createDesktopProjectSettingsAuthority,
  type DurableProjectSettingsAuthority,
} from '../../../node/settings/durable-project-settings';
import {
  inspectProjectConfigMigrations,
  migrateProjectConfigFromProvider,
} from '../../../node/settings/sharing/config-migration';
import {
  getProjectSettingsWriteTargets,
  resolveAllProjectSettingsTargets,
  resolveProjectSettingsTarget,
} from '../../../node/settings/sharing/project-settings-target-resolver';
import { shareProjectSettingsToConfig as writeSharedProjectSettingsToConfig } from '../../../node/settings/sharing/share-project-settings-to-config';
import {
  projectConfigDomainsFromState,
  type MigrateProjectConfigResult,
  type ProjectDurableSettingsDomains,
  type ProjectHostSettingsSnapshot,
  type ProjectSettingsDomainPatch,
  type ProjectSettingsError,
  type ProjectSettingsPage,
} from '../../project-settings-page';

export type ProjectSettingsHooks = {
  'project-settings:changed': (event: { projectId: string }) => void | Promise<void>;
};

export class ProjectSettingsService implements Hookable<ProjectSettingsHooks> {
  private readonly _hooks = new HookCore<ProjectSettingsHooks>((name, e) =>
    log.error(`ProjectSettingsService: ${String(name)} hook error`, { error: e })
  );
  private _disposeRendererBridge: (() => void) | null = null;
  private readonly durableSettings: DurableProjectSettingsAuthority;
  private readonly loadProject: (projectId: string) => Promise<Project | undefined>;
  private readonly clock: Clock;

  constructor(
    private readonly dependencies: {
      db: AppDb;
      projects: Pick<ProjectAttachmentManager, 'requireAttached'>;
      workspaceIdentity: WorkspaceIdentityService;
      durableSettings?: DurableProjectSettingsAuthority;
      loadProject?: (projectId: string) => Promise<Project | undefined>;
      clock?: Clock;
    }
  ) {
    this.durableSettings =
      dependencies.durableSettings ?? createDesktopProjectSettingsAuthority(dependencies.db);
    this.loadProject =
      dependencies.loadProject ?? ((projectId) => getProjectById(dependencies.db, projectId));
    this.clock = dependencies.clock ?? systemClock;
  }

  on<K extends keyof ProjectSettingsHooks>(name: K, handler: ProjectSettingsHooks[K]) {
    return this._hooks.on(name, handler);
  }

  initialize(): void {
    this._disposeRendererBridge?.();
    this._disposeRendererBridge = this.on('project-settings:changed', ({ projectId }) => {
      projectEvents.emit(undefined, { type: 'settings-changed', projectId });
    });
  }

  async getProjectConfigLiveSource(projectId: string): Promise<LiveSource> {
    const project = this.dependencies.projects.requireAttached(projectId);
    if (!project.success)
      throw new Error(`Project Host access is unavailable: ${project.error.type}`);
    const workspaceId = project.data.project.repositoryWorkspaceId;
    if (!workspaceId) throw new Error(`Project '${projectId}' has no repository workspace`);
    return project.data.workspaceRegistry.projectConfig
      .state({ workspaceId }, 'current')
      .asLiveSource();
  }

  async getProjectSettingsPage(
    projectId: string
  ): Promise<Result<ProjectSettingsPage, ProjectSettingsError>> {
    const record = await this.requireProjectRecord(projectId);
    if (!record.success) return record;
    const durable = await this.durableSettings.read(projectId);
    if (!durable.success) return durable;
    const project = this.dependencies.projects.requireAttached(projectId);
    if (!project.success) {
      return ok({
        durable: durable.data,
        host: { kind: 'never-observed' },
      });
    }
    return this.getProjectSettingsPageForProject(project.data, durable.data);
  }

  async updateProjectSettings(
    projectId: string,
    patch: ProjectSettingsDomainPatch
  ): Promise<Result<ProjectSettingsPage, ProjectSettingsError>> {
    const record = await this.requireProjectRecord(projectId);
    if (!record.success) return record;
    const hostPatch = hostSettingsPatch(patch);
    const project =
      Object.keys(hostPatch).length > 0
        ? this.dependencies.projects.requireAttached(projectId)
        : undefined;
    if (project && !project.success) return project;

    if (patch.gitIdentity || patch.placement?.stored.tmux !== undefined) {
      const durable = await this.durableSettings.patch(projectId, {
        ...(patch.gitIdentity ? { gitIdentity: patch.gitIdentity } : {}),
        ...(patch.placement && Object.hasOwn(patch.placement.stored, 'tmux')
          ? { placement: { stored: { tmux: patch.placement.stored.tmux } } }
          : {}),
      });
      if (!durable.success) return durable;
    }

    const personalPatch = {
      ...patch.lifecycle?.personal,
      ...patch.fileHandling?.personal,
    };
    if (Object.keys(personalPatch).length > 0) {
      if (!project?.success) return err({ type: 'error' });
      const workspaceId = project.data.project.repositoryWorkspaceId;
      if (!workspaceId) return err({ type: 'error' });
      const result = await project.data.workspaceRegistry.patchPersonalProjectConfig({
        workspaceId,
        patch: personalPatch,
      });
      if (!result.success) return err({ type: 'error' });
    }

    if (patch.placement && Object.hasOwn(patch.placement.stored, 'worktreeRoot')) {
      if (!project?.success) return err({ type: 'error' });
      const result = await project.data.settings.patch({
        placement: {
          stored: { worktreeRoot: patch.placement.stored.worktreeRoot },
        },
      });
      if (!result.success) return result;
    }

    const page = await this.getProjectSettingsPage(projectId);
    if (!page.success) return page;
    this.emitSettingsChanged(projectId);
    return page;
  }

  async shareProjectSettingsToConfig(
    projectId: string,
    request: WriteProjectConfigRequest
  ): Promise<Result<ProjectSettingsPage, ProjectSettingsError>> {
    const project = this.dependencies.projects.requireAttached(projectId);
    if (!project.success) return project;

    const resolvedTargets = await resolveAllProjectSettingsTargets(
      this.dependencies.db,
      this.dependencies.workspaceIdentity,
      project.data
    );
    const target = await resolveProjectSettingsTarget(
      this.dependencies.workspaceIdentity,
      project.data,
      request,
      resolvedTargets
    );
    if (!target) {
      return err({
        type: 'write-config-failed',
        message: 'Could not resolve the selected working copy.',
      });
    }
    const config = await this.resolveHostProjectConfig(project.data);
    if (!config.success) return config;
    const result = await writeSharedProjectSettingsToConfig(
      target,
      request.fields,
      config.data.personalConfig
    );
    if (!result.success) return result;
    if (!target.sourceWorkspaceId) return err({ type: 'error' });
    const refreshed = await project.data.workspaceRegistry.refreshProjectConfig({
      workspaceId: target.sourceWorkspaceId,
    });
    if (!refreshed.success) {
      log.warn('Failed to refresh shared project config', refreshed.error);
      return err({
        type: 'write-config-failed',
        message:
          `Wrote .hardcore.json, but failed to refresh shared project settings. ` +
          `Personal settings were not cleared.`,
      });
    }
    const cleared = await this.clearPersonalShareableFields(project.data, result.data);
    if (!cleared.success) {
      log.warn('Failed to clear shareable project settings', cleared.error);
      return err({
        type: 'write-config-failed',
        message: 'Wrote .hardcore.json, but failed to clear shared project settings.',
      });
    }

    const page = await this.getProjectSettingsPage(projectId);
    if (!page.success) return page;
    this.emitSettingsChanged(projectId);
    return page;
  }

  async migrateProjectConfig(
    projectId: string,
    request: MigrateProjectConfigRequest
  ): Promise<Result<MigrateProjectConfigResult, ProjectSettingsError>> {
    const project = this.dependencies.projects.requireAttached(projectId);
    if (!project.success) return project;

    const config = await this.resolveHostProjectConfig(project.data);
    if (!config.success) return config;
    if (hasConfiguredShareableProjectSettings(config.data.personalConfig)) {
      return err({
        type: 'write-config-failed',
        message: 'Shareable project settings are already configured.',
      });
    }

    const result = await migrateProjectConfigFromProvider(project.data, request, {
      patchPersonalConfig: (patch) =>
        project.data.workspaceRegistry
          .patchPersonalProjectConfig({
            workspaceId: config.data.repositoryId,
            patch,
          })
          .then((outcome) => (outcome.success ? ok(undefined) : err({ type: 'error' }))),
      clearPersonalFields: (fields) => this.clearPersonalShareableFields(project.data, fields),
    });
    if (!result.success) return result;

    const page = await this.getProjectSettingsPage(projectId);
    if (!page.success) return page;
    this.emitSettingsChanged(projectId);
    return ok({ page: page.data, migration: result.data });
  }

  private async requireProjectRecord(
    projectId: string
  ): Promise<Result<Project, UpdateProjectSettingsError>> {
    const project = await this.loadProject(projectId);
    return project ? ok(project) : err({ type: 'project-not-found' });
  }

  private async getProjectSettingsPageForProject(
    project: ProjectProvider,
    durable: ProjectDurableSettingsDomains
  ): Promise<Result<ProjectSettingsPage, ProjectSettingsError>> {
    const config = await this.resolveHostProjectConfig(project);
    if (!config.success) return config;
    const [placementContext, resolvedTargets] = await Promise.all([
      project.settings.getPlacementContext(),
      resolveAllProjectSettingsTargets(
        this.dependencies.db,
        this.dependencies.workspaceIdentity,
        project
      ),
    ]);
    const writeTargets = getProjectSettingsWriteTargets(resolvedTargets);
    const configMigrations = hasConfiguredShareableProjectSettings(config.data.personalConfig)
      ? []
      : await inspectProjectConfigMigrations(project);
    return ok({
      durable,
      host: {
        kind: 'observed',
        observedAt: this.clock.now(),
        value: {
          domains: projectHostSettingsDomains(config.data, durable, placementContext, writeTargets),
          configMigrations,
          shouldPromptConfigMigration: configMigrations.length > 0,
        },
      },
    });
  }

  private async resolveHostProjectConfig(
    project: ProjectProvider
  ): Promise<Result<ProjectConfigState, ProjectSettingsError>> {
    const workspaceId = project.project.repositoryWorkspaceId;
    if (!workspaceId) return err({ type: 'error' });
    const result = await project.workspaceRegistry.getProjectConfig({ workspaceId });
    if (!result.success) {
      log.warn('Failed to resolve host project config', {
        projectId: project.projectId,
        error: result.error,
      });
      return err({ type: 'error' });
    }
    return result;
  }

  private async clearPersonalShareableFields(
    project: ProjectProvider,
    clearShareableFields: WriteProjectConfigRequest['fields']
  ): Promise<Result<void, UpdateProjectSettingsError>> {
    const patch = tombstonePatchFor(clearShareableFields);
    if (Object.keys(patch).length === 0) return ok(undefined);
    const workspaceId = project.project.repositoryWorkspaceId;
    if (!workspaceId) return err({ type: 'error' });
    const result = await project.workspaceRegistry.patchPersonalProjectConfig({
      workspaceId,
      patch,
    });
    return result.success ? ok(undefined) : err({ type: 'error' });
  }

  private emitSettingsChanged(projectId: string): void {
    this._hooks.callHookBackground('project-settings:changed', { projectId });
  }
}

function projectHostSettingsDomains(
  config: ProjectConfigState,
  durable: ProjectDurableSettingsDomains,
  placementContext: PlacementContext,
  writeTargets: ProjectSettingsWriteTargetOption[]
): ProjectHostSettingsSnapshot['domains'] {
  const worktreeRoot = durable.placement.stored.worktreeRoot;
  const tmux = durable.placement.stored.tmux;
  return {
    ...projectConfigDomainsFromState(config, writeTargets),
    placement: {
      layers: placementContext,
      resolved: {
        worktreeRoot: resolveWorktreeRoot({
          projectWorktreeRoot: worktreeRoot,
          hostWorktreeRoot: placementContext.hostWorktreeRoot,
          builtInWorktreeRoot: placementContext.builtInWorktreeRoot,
          homeDirectory: placementContext.homeDirectory,
        }),
        tmux: resolveTmux({
          projectTmux: tmux,
          hostTmux: placementContext.hostTmux,
          appDefaultTmux: placementContext.appDefaultTmux,
        }),
      },
    },
  };
}

function hostSettingsPatch(patch: ProjectSettingsDomainPatch): ProjectSettingsDomainPatch {
  const worktreeRoot = patch.placement?.stored.worktreeRoot;
  return {
    ...(patch.lifecycle ? { lifecycle: patch.lifecycle } : {}),
    ...(patch.fileHandling ? { fileHandling: patch.fileHandling } : {}),
    ...(patch.placement && Object.hasOwn(patch.placement.stored, 'worktreeRoot')
      ? { placement: { stored: { worktreeRoot } } }
      : {}),
  };
}
