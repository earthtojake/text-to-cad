import { toBranchRef, type RepositorySelector } from '@emdash/core/runtimes/git/api';
import { err, ok, type Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import { hostPathFromNative, nativePathFromHost } from '@core/primitives/desktop-runtime/api';
import {
  remoteNameFromQualifiedRef,
  resolveBaseRefFromRemoteDefault,
} from '@core/primitives/git/api';
import type { CreateProjectError } from '@core/primitives/projects/api';
import type { GitRuntimeClient } from '@core/services/runtime-broker/api/clients';
import { gitErrorMessage, repositorySelector } from '@core/services/runtime-broker/node/git';

export async function resolveProjectBaseRef(
  git: GitRuntimeClient,
  repository: RepositorySelector,
  detectedBaseRef: string
): Promise<string> {
  const remoteName = remoteNameFromQualifiedRef(detectedBaseRef);
  if (!remoteName) return detectedBaseRef;

  try {
    const [defaultBranch, refs] = await Promise.all([
      git.repository.getDefaultBranch({ ...repository, remote: remoteName }),
      git.repository.model.state(repository, 'refs').snapshot(),
    ]);
    if (!defaultBranch.success) throw new Error(gitErrorMessage(defaultBranch.error));
    return resolveBaseRefFromRemoteDefault({
      detectedBaseRef,
      gitDefaultBranch: defaultBranch.data.branch ?? undefined,
      branches: refs.data.branches.map(toBranchRef),
    });
  } catch (error) {
    log.debug('Failed to resolve project base ref, using detected base ref', {
      detectedBaseRef,
      error,
    });
    return detectedBaseRef;
  }
}

export async function ensureProjectRepository(
  git: GitRuntimeClient,
  path: string,
  initGitRepository?: boolean
): Promise<Result<{ rootPath: string; baseRef: string }, CreateProjectError>> {
  const ensured = await git.ensureRepository({
    path: hostPathFromNative(path),
    options: { initIfMissing: initGitRepository ?? false },
  });
  if (!ensured.success) {
    return err({ ...ensured.error, path: nativePathFromHost(ensured.error.path) });
  }

  try {
    const rootPath = nativePathFromHost(ensured.data.rootPath);
    const repository = repositorySelector(rootPath);
    const baseRef = await resolveProjectBaseRef(git, repository, ensured.data.baseRef);
    return ok({ rootPath, baseRef });
  } catch (error) {
    return err({
      type: 'open-repository-failed',
      path: nativePathFromHost(ensured.data.rootPath),
      message: gitErrorMessage(error),
    });
  }
}
