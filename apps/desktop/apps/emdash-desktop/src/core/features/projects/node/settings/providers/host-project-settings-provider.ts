import os from 'node:os';
import path from 'node:path';
import type { Result } from '@emdash/shared';
import type { PlacementContext } from '@core/primitives/project-settings/api';
import type { UpdateProjectSettingsError } from '@core/primitives/projects/api';
import type { FilesClientScope } from '@core/services/runtime-broker/node/files';
import {
  normalizeWorktreeDirectory,
  resolveAndValidateWorktreeDirectory,
  type WorktreeDirectoryFileSystem,
} from '../worktree-directory';
import {
  DbProjectSettingsProvider,
  type DbProjectSettingsProviderOptions,
} from './db-project-settings-provider';

const pathPlatform = process.platform === 'win32' ? 'win32' : 'posix';

export type HostProjectSettingsProviderOptions = DbProjectSettingsProviderOptions & {
  placementContext(): Promise<PlacementContext>;
  worktreeDirectoryFileSystem: WorktreeDirectoryFileSystem;
};

export class HostProjectSettingsProvider extends DbProjectSettingsProvider {
  constructor(
    projectId: string,
    projectPath: string,
    /** Creation-time base ref (creation provenance); null when unknown. */
    defaultBranchFallback: string | null,
    files: FilesClientScope,
    private readonly hostOptions: HostProjectSettingsProviderOptions
  ) {
    super(projectId, projectPath, defaultBranchFallback, files, path.join, hostOptions);
  }

  protected placementContext(): Promise<PlacementContext> {
    return this.hostOptions.placementContext();
  }

  protected validateWorktreeDirectory(
    worktreeDirectory: string | undefined
  ): Promise<Result<string | undefined, UpdateProjectSettingsError>> {
    return resolveAndValidateWorktreeDirectory(worktreeDirectory, {
      pathApi: path,
      pathPlatform,
      fs: this.hostOptions.worktreeDirectoryFileSystem,
      homeDirectory: os.homedir(),
    });
  }

  protected normalizeStoredWorktreeDirectory(
    worktreeDirectory: string
  ): Promise<Result<string, UpdateProjectSettingsError>> {
    return normalizeWorktreeDirectory(worktreeDirectory, {
      pathApi: path,
      pathPlatform,
      homeDirectory: os.homedir(),
    });
  }
}
