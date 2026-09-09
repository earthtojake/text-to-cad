import type { HostRef } from '@emdash/core/primitives/host/api';
import { absoluteDirname, type HostAbsolutePath } from '@emdash/core/primitives/path/api';
import type { HostRuntimesClient, RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { err, ok, type Result } from '@emdash/shared';
import type { WorkspacePlacementResolver } from '@core/features/workspaces/api/node/placement/workspace-placement-resolver';
import {
  fileKeyForAbsolutePath,
  hostPathFromNative,
  nativePathFromHost,
} from '@core/primitives/desktop-runtime/api';
import type { ProjectPlacementError } from '@core/primitives/projects/api';
import { fsErrorMessage } from '@core/services/runtime-broker/node/files';

type EnsureDefaultRepositoriesRootDependencies = {
  placement: Pick<WorkspacePlacementResolver, 'resolveRepositoriesRoot'>;
  runtimes: Pick<RuntimeBroker, 'client'>;
};

type HostFiles = HostRuntimesClient['files'];

export async function ensureDefaultRepositoriesRoot(
  dependencies: EnsureDefaultRepositoriesRootDependencies,
  host: HostRef
): Promise<Result<string, ProjectPlacementError>> {
  const rootResult = await dependencies.placement.resolveRepositoriesRoot(host);
  if (!rootResult.success) return rootResult;

  const runtime = await dependencies.runtimes.client(host);
  if (!runtime.success) return runtime;

  const root = hostPathFromNative(rootResult.data);
  const ensured = await ensureDirectory(runtime.data.files, root);
  if (!ensured.success) return ensured;
  return ok(rootResult.data);
}

async function ensureDirectory(
  files: HostFiles,
  root: HostAbsolutePath
): Promise<Result<void, ProjectPlacementError>> {
  const missingDirectories: HostAbsolutePath[] = [];
  let candidate = root;

  for (;;) {
    const key = fileKeyForAbsolutePath(candidate);
    const exists = await files.fs.exists(key);
    if (exists.success && exists.data.exists) break;
    if (!exists.success && exists.error.type !== 'not-found') {
      return filesystemUnavailable(candidate, exists.error);
    }

    missingDirectories.push(candidate);
    const parent = absoluteDirname(candidate);
    if (!parent) {
      return err({
        type: 'filesystem-unavailable',
        path: nativePathFromHost(candidate),
        message: 'Could not find an existing ancestor for the repositories root',
      });
    }
    candidate = parent;
  }

  for (let index = missingDirectories.length - 1; index >= 0; index -= 1) {
    const directory = missingDirectories[index];
    if (!directory) continue;
    const created = await files.fs.createDirectory(fileKeyForAbsolutePath(directory));
    if (!created.success && created.error.type !== 'already-exists') {
      return filesystemUnavailable(directory, created.error);
    }
  }

  return ok();
}

function filesystemUnavailable(
  path: HostAbsolutePath,
  error: Parameters<typeof fsErrorMessage>[0]
): Result<never, ProjectPlacementError> {
  return err({
    type: 'filesystem-unavailable',
    path: nativePathFromHost(path),
    message: fsErrorMessage(error),
  });
}
