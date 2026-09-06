import type { PersonalProjectConfig } from '@emdash/core/runtimes/workspace-registry/api';
import { ok, type Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import type { ShareableProjectSettingsWriteField } from '@core/primitives/project-settings/api';
import type { UpdateProjectSettingsError } from '@core/primitives/projects/api';
import { fileKey, fsErrorMessage } from '@core/services/runtime-broker/node/files';
import { errorMessage, writeConfigFailed } from './config-migration-utils';
import type { ProjectSettingsResolvedTarget } from './project-settings-target-resolver';
import {
  CONFIG_FILE,
  parseWorkspaceConfigObject,
  patchShareableProjectSettingsFields,
} from './workspace-config-file';

export async function shareProjectSettingsToConfig(
  target: ProjectSettingsResolvedTarget,
  fields: ShareableProjectSettingsWriteField[],
  personalConfig: PersonalProjectConfig
): Promise<Result<ShareableProjectSettingsWriteField[], UpdateProjectSettingsError>> {
  try {
    let config: Record<string, unknown>;
    try {
      const exists = await target.files.client.fs.exists(fileKey(target.files, target.configPath));
      if (!exists.success) {
        const message = `Could not check existing ${CONFIG_FILE}: ${fsErrorMessage(exists.error)}`;
        log.warn('Failed to check project config before writing', exists.error);
        return writeConfigFailed(message);
      }
      if (exists.data.exists) {
        const content = await target.files.client.fs.readText(
          fileKey(target.files, target.configPath)
        );
        if (!content.success) {
          const message = `Could not read existing ${CONFIG_FILE}: ${fsErrorMessage(content.error)}`;
          log.warn('Failed to read project config before writing', content.error);
          return writeConfigFailed(message);
        }
        if (content.data.truncated) {
          const message = `Could not read existing ${CONFIG_FILE}: file was truncated.`;
          log.warn('Project config was truncated before writing', {
            path: target.configPath,
            totalSize: content.data.totalSize,
          });
          return writeConfigFailed(message);
        }
        config = parseWorkspaceConfigObject(content.data.content);
      } else {
        config = {};
      }
    } catch (error) {
      const message = `Could not read existing ${CONFIG_FILE}: ${errorMessage(error)}`;
      log.warn('Failed to read project config before writing', { error });
      return writeConfigFailed(message);
    }

    const writtenFields = patchShareableProjectSettingsFields(config, personalConfig, fields);

    const written = await target.files.client.fs.writeFile({
      ...fileKey(target.files, target.configPath),
      content: `${JSON.stringify(config, null, 2)}\n`,
      precondition: { kind: 'overwrite' },
    });
    if (!written.success) {
      log.warn('Failed to write project config to repo', written.error);
      return writeConfigFailed(`Could not write ${CONFIG_FILE}: ${fsErrorMessage(written.error)}`);
    }

    return ok(writtenFields);
  } catch (error) {
    log.warn('Failed to write project config to repo', { error });
    return writeConfigFailed(errorMessage(error));
  }
}
