import { emdashConfigSchema } from '@emdash/core/primitives/emdash-config/api';
import { err, ok, type Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import type {
  ProjectSettingsProvider,
  StoredPlacementSettings,
} from '@core/features/projects/api/node/settings/provider';
import type { ProjectSettingsDomainPatch } from '@core/features/projects/api/project-settings-page';
import {
  resolveTmux as resolveEffectiveTmux,
  type PlacementContext,
  type RepoFacts,
  type StoredBaseProjectSettings,
  type StoredProjectGitSettings,
} from '@core/primitives/project-settings/api';
import type { UpdateProjectSettingsError } from '@core/primitives/projects/api';
import type { FilesClientScope } from '@core/services/runtime-broker/node/files';
import {
  migrateAncientProjectConfig,
  type ProjectSettingsGitInspector,
} from '../migrations/ancient-project-config';
import { serializeShareableProjectSettings } from '../migrations/legacy-shareable-marker';
import {
  hasLegacyLifecycleSettings,
  legacyBaseProjectSettingsSchema,
  legacyLifecycleSettingsFromStored,
  withLegacyLifecycleSettings,
  type LegacyBaseProjectSettings,
  type LegacyLifecycleSettings,
} from '../migrations/legacy-stored-project-settings';
import type { ProjectSettingsMigrationReader } from '../migrations/migration-reader';
import { migrateStoredBaseProjectSettings } from '../migrations/stored-settings';
import { compactUndefined, readJson } from '../project-settings-json';
import type { ProjectSettingsStorage, StoredProjectSettings } from '../project-settings-storage';
import { CONFIG_FILE } from '../sharing/workspace-config-file';

export type DbProjectSettingsProviderOptions = {
  git?: ProjectSettingsGitInspector;
  storage: ProjectSettingsStorage;
  /**
   * Repository facts for the lazy demote-if-matches-inference migration
   * (spec: github-git-settings §10). Absent or failing means demotion is
   * skipped this read and retried on the next one.
   */
  getRepoFacts?: () => Promise<RepoFacts | null>;
};

export abstract class DbProjectSettingsProvider
  implements ProjectSettingsProvider, ProjectSettingsMigrationReader
{
  private ancientConfigMigrationPromise: Promise<void> | undefined;

  protected constructor(
    private readonly projectId: string,
    protected readonly projectPath: string,
    /** Creation-time base ref (creation provenance); null when unknown. */
    protected readonly defaultBranchFallback: string | null,
    private readonly configFiles: FilesClientScope | undefined,
    private readonly joinProjectPath: (rootPath: string, relPath: string) => string,
    private readonly options: DbProjectSettingsProviderOptions
  ) {}

  protected abstract placementContext(): Promise<PlacementContext>;

  protected abstract validateWorktreeDirectory(
    worktreeDirectory: string | undefined
  ): Promise<Result<string | undefined, UpdateProjectSettingsError>>;

  protected abstract normalizeStoredWorktreeDirectory(
    worktreeDirectory: string
  ): Promise<Result<string, UpdateProjectSettingsError>>;

  /**
   * New rows carry only explicit choices (spec: github-git-settings §10):
   * defaultBranch/baseRemote are no longer seeded — the branch detected at
   * creation survives only as creation provenance (`defaultBranchFallback`).
   * Tmux is also inferred from host/app layers and is no longer materialized.
   */
  protected async initialBaseProjectSettings(): Promise<StoredBaseProjectSettings> {
    return {};
  }

  private projectFilePath(relPath: string): string {
    return this.joinProjectPath(this.projectPath, relPath);
  }

  private async ensureRow(): Promise<void> {
    if (await this.options.storage.get(this.projectId)) return;

    const baseSettings = await this.initialBaseProjectSettings();
    // No built-in preserve defaults (spec: workspace-lifecycle-v2): new projects
    // start with empty shareable settings; preservePatterns is a deliberate choice.
    await this.options.storage.insertIfMissing(this.projectId, {
      baseProjectSettingsJson: JSON.stringify(compactUndefined(baseSettings)),
      shareableProjectSettingsJson: serializeShareableProjectSettings({}),
      legacyConfigMigratedAt: null,
    });
  }

  private async readSettingsRow(placementContext?: PlacementContext): Promise<{
    stored: StoredBaseProjectSettings;
    legacyLifecycle: LegacyLifecycleSettings;
  }> {
    await this.ensureRow();
    const row = await this.options.storage.get(this.projectId);
    if (!row) {
      const stored = await this.initialBaseProjectSettings();
      return {
        stored,
        legacyLifecycle: {},
      };
    }
    const rawBase = readJson(
      row.baseProjectSettingsJson,
      legacyBaseProjectSettingsSchema,
      'base project settings'
    );
    const rawShareable = readJson(
      row.shareableProjectSettingsJson,
      emdashConfigSchema,
      'legacy shareable project settings'
    );
    const legacyLifecycle = legacyLifecycleSettingsFromStored(rawBase, rawShareable);
    const stored = await this.migrateStoredModelIfNeeded(
      row,
      rawBase,
      rawShareable,
      legacyLifecycle,
      placementContext
    );

    return {
      stored,
      legacyLifecycle,
    };
  }

  private legacyLifecycleFromRow(row: StoredProjectSettings): LegacyLifecycleSettings {
    return legacyLifecycleSettingsFromStored(
      readJson(
        row.baseProjectSettingsJson,
        legacyBaseProjectSettingsSchema,
        'base project settings'
      ),
      readJson(
        row.shareableProjectSettingsJson,
        emdashConfigSchema,
        'legacy shareable project settings'
      )
    );
  }

  private baseJsonForWrite(
    base: StoredBaseProjectSettings,
    row: StoredProjectSettings | undefined
  ): string {
    const legacyLifecycle = row ? this.legacyLifecycleFromRow(row) : {};
    return JSON.stringify(compactUndefined(withLegacyLifecycleSettings(base, legacyLifecycle)));
  }

  /**
   * Lazy read-path migrations (spec: github-git-settings §10): converts a raw
   * row to the stored model and writes the migrated row back when it changed.
   * A failed write-back degrades to the in-memory migrated view and retries
   * on the next read.
   */
  private async migrateStoredModel(
    raw: LegacyBaseProjectSettings,
    placementContext?: PlacementContext
  ): Promise<{ next: StoredBaseProjectSettings; changed: boolean }> {
    const needsFacts =
      raw.defaultBranch !== undefined || raw.baseRemote !== undefined || raw.remote !== undefined;
    const needsTmuxDefault = raw.tmuxDefaultMigrated !== true;
    const [repoFacts, placement] = await Promise.all([
      needsFacts ? this.loadRepoFacts() : Promise.resolve(null),
      needsTmuxDefault
        ? placementContext
          ? Promise.resolve(placementContext)
          : this.placementContext()
        : Promise.resolve(null),
    ]);
    return migrateStoredBaseProjectSettings(raw, repoFacts, {
      ...(placement
        ? {
            tmuxDefault: resolveEffectiveTmux({
              hostTmux: placement.hostTmux,
              appDefaultTmux: placement.appDefaultTmux,
            }).value,
          }
        : {}),
    });
  }

  private async migrateStoredModelIfNeeded(
    row: StoredProjectSettings,
    rawBase: LegacyBaseProjectSettings,
    rawShareable: ReturnType<typeof emdashConfigSchema.parse>,
    legacyLifecycle: LegacyLifecycleSettings,
    placementContext?: PlacementContext
  ): Promise<StoredBaseProjectSettings> {
    const { next, changed: baseChanged } = await this.migrateStoredModel(rawBase, placementContext);
    if (hasLegacyLifecycleSettings(legacyLifecycle)) {
      if (baseChanged) {
        try {
          await this.options.storage.update(this.projectId, {
            baseProjectSettingsJson: this.baseJsonForWrite(next, row),
          });
        } catch (error) {
          log.warn('Failed to write back migrated project settings; retrying next read', {
            projectId: this.projectId,
            error,
          });
        }
      }
      return next;
    }

    const shareableChanged = Object.keys(rawShareable).length > 0;
    if (baseChanged || shareableChanged) {
      try {
        await this.options.storage.update(this.projectId, {
          ...(baseChanged
            ? { baseProjectSettingsJson: JSON.stringify(compactUndefined(next)) }
            : {}),
          ...(shareableChanged
            ? {
                shareableProjectSettingsJson: serializeShareableProjectSettings(
                  {},
                  { previousRaw: row.shareableProjectSettingsJson }
                ),
              }
            : {}),
        });
      } catch (error) {
        log.warn('Failed to write back migrated project settings; retrying next read', {
          projectId: this.projectId,
          error,
        });
      }
    }
    return next;
  }

  private async loadRepoFacts(): Promise<RepoFacts | null> {
    if (!this.options.getRepoFacts) return null;
    try {
      return await this.options.getRepoFacts();
    } catch (error) {
      log.warn('Failed to load repo facts for settings migration; skipping demotion', {
        projectId: this.projectId,
        error,
      });
      return null;
    }
  }

  async migrateAncientConfig(git = this.options.git): Promise<void> {
    if (this.ancientConfigMigrationPromise) {
      await this.ancientConfigMigrationPromise;
      return;
    }

    this.ancientConfigMigrationPromise = (async () => {
      await this.ensureRow();
      const row = await this.options.storage.get(this.projectId);
      await migrateAncientProjectConfig({
        projectId: this.projectId,
        row,
        configFiles: this.configFiles,
        configPath: this.projectFilePath(CONFIG_FILE),
        defaultBranchFallback: this.defaultBranchFallback,
        storage: this.options.storage,
        git,
        normalizeStoredWorktreeDirectory: (worktreeDirectory) =>
          this.normalizeStoredWorktreeDirectory(worktreeDirectory),
      });
    })();

    try {
      await this.ancientConfigMigrationPromise;
    } catch (error) {
      this.ancientConfigMigrationPromise = undefined;
      throw error;
    }
  }

  async ensure(): Promise<void> {
    await this.ensureRow();
  }

  async readLegacyLifecycleSettings(): Promise<LegacyLifecycleSettings> {
    return (await this.readSettingsRow()).legacyLifecycle;
  }

  async finalizeLegacyLifecycleSettings(): Promise<void> {
    await this.ensureRow();
    const row = await this.options.storage.get(this.projectId);
    if (!row) return;
    const rawBase = readJson(
      row.baseProjectSettingsJson,
      legacyBaseProjectSettingsSchema,
      'base project settings'
    );
    const rawShareable = readJson(
      row.shareableProjectSettingsJson,
      emdashConfigSchema,
      'legacy shareable project settings'
    );
    const { next: base, changed: baseChanged } = await this.migrateStoredModel(rawBase);
    const legacyLifecycle = legacyLifecycleSettingsFromStored(rawBase, rawShareable);
    const shareableChanged = Object.keys(rawShareable).length > 0;
    if (!baseChanged && !hasLegacyLifecycleSettings(legacyLifecycle) && !shareableChanged) return;

    await this.options.storage.update(this.projectId, {
      ...(baseChanged || hasLegacyLifecycleSettings(legacyLifecycle)
        ? { baseProjectSettingsJson: JSON.stringify(compactUndefined(base)) }
        : {}),
      ...(shareableChanged
        ? {
            shareableProjectSettingsJson: serializeShareableProjectSettings(
              {},
              { previousRaw: row.shareableProjectSettingsJson }
            ),
          }
        : {}),
    });
  }

  /**
   * The stored git settings in the new model (spec: github-git-settings §2):
   * only explicit user choices, absence = infer. This is the resolver input;
   * adoption code should consume this instead of the legacy `get()` view.
   */
  async getStoredGitSettings(): Promise<StoredProjectGitSettings> {
    const { stored } = await this.readSettingsRow();
    return {
      ...(stored.defaultBranch !== undefined ? { defaultBranch: stored.defaultBranch } : {}),
      ...(stored.baseRemote !== undefined ? { baseRemote: stored.baseRemote } : {}),
      ...(stored.pushRemote !== undefined ? { pushRemote: stored.pushRemote } : {}),
      ...(stored.githubAccount !== undefined ? { githubAccount: stored.githubAccount } : {}),
      ...(stored.agentGitCredentials !== undefined
        ? { agentGitCredentials: stored.agentGitCredentials }
        : {}),
      ...(stored.worktreeRoot !== undefined ? { worktreeRoot: stored.worktreeRoot } : {}),
    };
  }

  async getStoredPlacementSettings(): Promise<StoredPlacementSettings> {
    const { stored } = await this.readSettingsRow();
    return stored.tmux === undefined ? {} : { tmux: stored.tmux };
  }

  async patch(
    patch: Pick<ProjectSettingsDomainPatch, 'gitIdentity' | 'placement'>
  ): Promise<Result<void, UpdateProjectSettingsError>> {
    try {
      const { stored } = await this.readSettingsRow();
      const next: StoredBaseProjectSettings = { ...stored };
      const git = patch.gitIdentity?.stored;
      if (git) {
        for (const field of [
          'defaultBranch',
          'baseRemote',
          'pushRemote',
          'githubAccount',
          'agentGitCredentials',
        ] as const) {
          if (!Object.hasOwn(git, field)) continue;
          const value = git[field];
          if (value === null || value === undefined) {
            delete next[field];
          } else {
            next[field] = value as never;
          }
        }
      }

      const placement = patch.placement?.stored;
      if (placement && Object.hasOwn(placement, 'worktreeRoot')) {
        const worktreeRoot = placement.worktreeRoot ?? undefined;
        const validated = await this.validateWorktreeDirectory(worktreeRoot);
        if (!validated.success) return validated;
        if (validated.data === undefined) delete next.worktreeRoot;
        else next.worktreeRoot = validated.data;
      }
      if (placement && Object.hasOwn(placement, 'tmux')) {
        if (placement.tmux === null || placement.tmux === undefined) delete next.tmux;
        else next.tmux = placement.tmux;
      }

      await this.ensure();
      const row = await this.options.storage.get(this.projectId);
      await this.options.storage.update(this.projectId, {
        baseProjectSettingsJson: this.baseJsonForWrite(next, row),
      });
      return ok();
    } catch (error) {
      log.warn('Failed to patch project settings domains', { error });
      return err({ type: 'error' });
    }
  }

  async getPlacementContext(): Promise<PlacementContext> {
    return this.placementContext();
  }

  async resolveTmux() {
    const placement = await this.placementContext();
    const { stored } = await this.readSettingsRow(placement);
    return resolveEffectiveTmux({
      projectTmux: stored.tmux,
      hostTmux: placement.hostTmux,
      appDefaultTmux: placement.appDefaultTmux,
    });
  }
}
