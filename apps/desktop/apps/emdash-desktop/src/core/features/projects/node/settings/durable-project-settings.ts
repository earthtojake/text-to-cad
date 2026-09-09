import { err, ok, type Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import type {
  ProjectDurableSettingsDomains,
  ProjectSettingsDomainPatch,
} from '@core/features/projects/api/project-settings-page';
import {
  storedBaseProjectSettingsSchema,
  type StoredBaseProjectSettings,
} from '@core/primitives/project-settings/api';
import type { UpdateProjectSettingsError } from '@core/primitives/projects/api';
import { compactUndefined, readJson } from './project-settings-json';
import { ProjectSettingsRepository, type ProjectSettingsStorage } from './project-settings-storage';

export interface DurableProjectSettingsAuthority {
  read(
    projectId: string
  ): Promise<Result<ProjectDurableSettingsDomains, UpdateProjectSettingsError>>;
  patch(
    projectId: string,
    patch: Pick<ProjectSettingsDomainPatch, 'gitIdentity' | 'placement'>
  ): Promise<Result<void, UpdateProjectSettingsError>>;
}

export class DesktopProjectSettingsAuthority implements DurableProjectSettingsAuthority {
  constructor(private readonly storage: ProjectSettingsStorage) {}

  async read(
    projectId: string
  ): Promise<Result<ProjectDurableSettingsDomains, UpdateProjectSettingsError>> {
    try {
      const stored = await this.readStored(projectId);
      return ok(durableDomains(stored));
    } catch (error) {
      log.warn('Failed to read durable Project settings', { projectId, error });
      return err({ type: 'invalid-settings' });
    }
  }

  async patch(
    projectId: string,
    patch: Pick<ProjectSettingsDomainPatch, 'gitIdentity' | 'placement'>
  ): Promise<Result<void, UpdateProjectSettingsError>> {
    try {
      const row = await this.storage.get(projectId);
      const stored = row ? await this.readStored(projectId) : {};
      const next = { ...stored };
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
          if (value === null || value === undefined) delete next[field];
          else next[field] = value as never;
        }
      }
      const tmux = patch.placement?.stored.tmux;
      if (patch.placement && Object.hasOwn(patch.placement.stored, 'tmux')) {
        if (tmux === null || tmux === undefined) delete next.tmux;
        else next.tmux = tmux;
      }

      if (!row) {
        await this.storage.insertIfMissing(projectId, {
          baseProjectSettingsJson: '{}',
          shareableProjectSettingsJson: '{}',
          legacyConfigMigratedAt: null,
        });
      }
      const current = row ?? (await this.storage.get(projectId));
      if (!current) throw new Error(`Failed to create Project settings row for ${projectId}`);
      await this.storage.update(projectId, {
        baseProjectSettingsJson: JSON.stringify(compactUndefined(next)),
      });
      return ok();
    } catch (error) {
      log.warn('Failed to patch durable Project settings', { projectId, error });
      return err({ type: 'error' });
    }
  }

  private async readStored(projectId: string) {
    const row = await this.storage.get(projectId);
    if (!row) return {};
    const raw = readJson(
      row.baseProjectSettingsJson,
      storedBaseProjectSettingsSchema,
      'base project settings'
    );
    return raw;
  }
}

export function createDesktopProjectSettingsAuthority(
  db: ConstructorParameters<typeof ProjectSettingsRepository>[0]
): DesktopProjectSettingsAuthority {
  return new DesktopProjectSettingsAuthority(new ProjectSettingsRepository(db));
}

function durableDomains(stored: StoredBaseProjectSettings): ProjectDurableSettingsDomains {
  const { worktreeRoot, tmux, ...gitIdentity } = stored;
  return {
    gitIdentity: { stored: gitIdentity },
    placement: {
      stored: {
        ...(worktreeRoot !== undefined ? { worktreeRoot } : {}),
        ...(tmux !== undefined ? { tmux } : {}),
      },
    },
  };
}
