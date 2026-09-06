import { hostRef, LOCAL_HOST_REF, type HostRef } from '@emdash/core/primitives/host/api';
import { filesContract } from '@emdash/core/runtimes/files/api';
import { gitContract, type GitTransferProgress } from '@emdash/core/runtimes/git/api';
import type { HostRuntimesClient } from '@emdash/core/services/runtime-broker/api';
import { err, ok, type Result } from '@emdash/shared';
import { log } from '@emdash/shared/logger';
import { LiveJobCancelledError, type LiveJobContext } from '@emdash/wire/live';
import type { GitCredentialsService } from '@core/features/github/api/node/services/git-credentials-service';
import type {
  CreateProjectFromRemoteInput,
  ProjectCreationJobError,
  ProjectCreationProgress,
  ProjectCreationState,
  ProjectHostParams,
} from '@core/features/projects/api';
import {
  type CreateProjectDependencies,
  createProject,
} from '@core/features/projects/node/operations/create-project';
import { formatCloneErrorDetail } from '@core/features/source-control/api/git-error-messages';
import { fileKeyForAbsolutePath, hostPathFromNative } from '@core/primitives/desktop-runtime/api';
import type { Project } from '@core/primitives/projects/api';
import { fsErrorMessage } from '@core/services/runtime-broker/node/files';
import { runRuntimeLiveJob } from '@core/services/runtime-clients/node/live-job';

export type ProjectCreationPublisher = (projectId: string, state: ProjectCreationState) => void;

type HostFiles = HostRuntimesClient['files'];

export type CreateProjectFromRemoteDependencies = CreateProjectDependencies & {
  /** Emdash credential helper for HTTPS clones (spec: github-git-settings §4). */
  mintCloneCredentials: GitCredentialsService['mintCloneCredentials'];
};

export async function createProjectFromRemote(
  dependencies: CreateProjectFromRemoteDependencies,
  input: CreateProjectFromRemoteInput,
  ctx: LiveJobContext<ProjectCreationProgress>,
  publishCreationState: ProjectCreationPublisher
) {
  const host = hostRefForProjectHost(input.host);
  const runtime = await dependencies.runtimes.client(host);
  if (!runtime.success) {
    const error = creationError(runtime.error.type, runtime.error.message);
    publishCreationState(input.projectId, { phase: 'error', message: error.message, error });
    return { success: false as const, error };
  }

  const files = runtime.data.files;
  const targetInspection = await inspectTarget(files, input.targetPath);
  if (!targetInspection.success) {
    publishCreationState(input.projectId, {
      phase: 'error',
      message: targetInspection.error.message,
      error: targetInspection.error,
    });
    return { success: false as const, error: targetInspection.error };
  }
  const targetStatus = targetInspection.data;
  if (targetStatus === 'non-empty') {
    const error = creationError(
      'destination-not-empty',
      `Clone destination is not empty: ${input.targetPath}`
    );
    publishCreationState(input.projectId, { phase: 'error', message: error.message, error });
    return { success: false as const, error };
  }
  const targetExistedBeforeClone = targetStatus === 'empty-directory';
  publishCreationState(input.projectId, { phase: 'cloning', message: 'Cloning repository…' });

  const credentialLease = await dependencies.mintCloneCredentials({
    repositoryUrl: input.repositoryUrl,
    host,
  });
  let clone: Awaited<ReturnType<typeof runRuntimeLiveJob<typeof gitContract.cloneRepository>>>;
  try {
    clone = await runRuntimeLiveJob(
      gitContract.cloneRepository,
      runtime.data.git.cloneRepository,
      {
        repositoryUrl: input.repositoryUrl,
        targetPath: hostPathFromNative(input.targetPath),
        credentials: credentialLease?.credentials,
      },
      (progress) => {
        const mapped = cloneProgressToCreationProgress(progress);
        ctx.progress(mapped);
        publishCreationState(input.projectId, {
          phase: 'cloning',
          message: mapped.message,
        });
      },
      { signal: ctx.signal }
    );
  } catch (error) {
    if (error instanceof LiveJobCancelledError || ctx.signal.aborted) {
      if (!targetExistedBeforeClone) {
        await cleanupCancelledCloneTarget(files, input.targetPath);
      }
      const cancelled = creationError('cancelled', 'Project creation was cancelled');
      publishCreationState(input.projectId, {
        phase: 'error',
        message: cancelled.message,
        error: cancelled,
      });
      return { success: false as const, error: cancelled };
    }
    throw error;
  } finally {
    credentialLease?.release();
  }
  if (!clone.success) {
    const error = creationError(
      clone.error.type,
      formatCloneErrorDetail(clone.error, { isSshProject: input.host.type === 'ssh' })
    );
    publishCreationState(input.projectId, { phase: 'error', message: error.message, error });
    return { success: false as const, error };
  }

  publishCreationState(input.projectId, {
    phase: 'registering',
    message: 'Registering project…',
  });
  ctx.progress({ phase: 'registering', message: 'Registering project…' });
  const project = await createProject(
    dependencies,
    input.host.type === 'ssh'
      ? {
          type: 'ssh',
          id: input.projectId,
          name: input.name,
          path: input.targetPath,
          connectionId: input.host.connectionId,
        }
      : {
          type: 'local',
          id: input.projectId,
          name: input.name,
          path: input.targetPath,
        }
  );
  if (!project.success) {
    const error = projectErrorToCreationError(project.error);
    publishCreationState(input.projectId, {
      phase: 'error',
      message: error.message,
      error,
    });
    return { success: false as const, error };
  }

  publishCreationState(input.projectId, { phase: 'ready', project: project.data });
  return { success: true as const, data: project.data satisfies Project };
}

async function inspectTarget(
  files: HostFiles,
  path: string
): Promise<Result<'missing' | 'empty-directory' | 'non-empty', ProjectCreationJobError>> {
  const key = fileKeyForAbsolutePath(hostPathFromNative(path));
  const exists = await files.fs.exists(key);
  if (!exists.success) {
    return exists.error.type === 'not-found'
      ? ok('missing')
      : err(creationError('inspect-failed', fsErrorMessage(exists.error)));
  }
  if (!exists.data.exists) return ok('missing');

  const pathEntry = await files.fs.stat(key);
  if (!pathEntry.success) {
    return pathEntry.error.type === 'not-found'
      ? ok('missing')
      : err(creationError('inspect-failed', fsErrorMessage(pathEntry.error)));
  }
  if (pathEntry.data.type !== 'directory') return ok('non-empty');

  const listed = await runRuntimeLiveJob(filesContract.fs.enumerate, files.fs.enumerate, {
    path: hostPathFromNative(path),
  });
  if (!listed.success) {
    return err(creationError('inspect-failed', fsErrorMessage(listed.error)));
  }
  return ok(listed.data.paths.length === 0 ? 'empty-directory' : 'non-empty');
}

async function cleanupCancelledCloneTarget(files: HostFiles, path: string): Promise<void> {
  try {
    await files.fs.delete({
      ...fileKeyForAbsolutePath(hostPathFromNative(path)),
      recursive: true,
    });
  } catch (error) {
    log.warn('Failed to clean up cancelled project clone target', {
      path,
      error: error instanceof Error ? error.message : String(error),
    });
  }
}

function hostRefForProjectHost(host: ProjectHostParams): HostRef {
  return host.type === 'ssh' ? hostRef('remote', host.connectionId) : LOCAL_HOST_REF;
}

function cloneProgressToCreationProgress(progress: GitTransferProgress): ProjectCreationProgress {
  return {
    phase: 'cloning',
    percent: progress.percent,
    message: progress.detail ? `${progress.phase}: ${progress.detail}` : progress.phase,
  };
}

function creationError(type: string, message: string): ProjectCreationJobError {
  return { type, message };
}

function projectErrorToCreationError(error: unknown): ProjectCreationJobError {
  if (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as { type?: unknown }).type === 'string'
  ) {
    const projectError = error as { type: string; path?: string; message?: string };
    return creationError(
      projectError.type,
      projectError.message ??
        `Project creation failed${projectError.path ? `: ${projectError.path}` : ''}`
    );
  }
  return unknownToProjectCreationError(error);
}

export function unknownToProjectCreationError(error: unknown): ProjectCreationJobError {
  if (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as { type?: unknown }).type === 'string' &&
    typeof (error as { message?: unknown }).message === 'string'
  ) {
    return error as ProjectCreationJobError;
  }
  return creationError(
    'project-creation-failed',
    error instanceof Error ? error.message : String(error)
  );
}
