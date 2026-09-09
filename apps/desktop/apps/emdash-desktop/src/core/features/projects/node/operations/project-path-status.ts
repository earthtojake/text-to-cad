import type { HostRef } from '@emdash/core/primitives/host/api';
import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import {
  fileKeyForAbsolutePath,
  hostPathFromNative,
  nativePathFromHost,
} from '@core/primitives/desktop-runtime/api';
import type { ProjectPathStatus } from '@core/primitives/projects/api';
import { fsErrorMessage } from '@core/services/runtime-broker/node/files';

export async function getProjectPathStatus(
  dependencies: { runtimes: Pick<RuntimeBroker, 'client'> },
  host: HostRef,
  path: string
): Promise<ProjectPathStatus> {
  try {
    const runtime = await dependencies.runtimes.client(host);
    if (!runtime.success) {
      return { isDirectory: false, isGitRepo: false, error: runtime.error };
    }

    const absolutePath = hostPathFromNative(path);
    const pathEntry = await runtime.data.files.fs.stat(fileKeyForAbsolutePath(absolutePath));
    if (!pathEntry.success) {
      if (pathEntry.error.type === 'not-found') {
        return { isDirectory: false, isGitRepo: false };
      }
      return {
        isDirectory: false,
        isGitRepo: false,
        error: { type: 'inspect-failed', path, message: fsErrorMessage(pathEntry.error) },
      };
    }
    if (pathEntry.data.type !== 'directory') {
      return { isDirectory: false, isGitRepo: false };
    }

    const inspection = await runtime.data.git.inspectPath({ path: absolutePath });
    if (!inspection.success) {
      return {
        isDirectory: true,
        isGitRepo: false,
        error: {
          type: 'inspect-failed',
          path: nativePathFromHost(inspection.error.path),
          message: inspection.error.message,
        },
      };
    }
    return { isDirectory: true, isGitRepo: inspection.data.kind === 'repository' };
  } catch (error) {
    return {
      isDirectory: false,
      isGitRepo: false,
      error: { type: 'inspect-failed', path, message: String(error) },
    };
  }
}
