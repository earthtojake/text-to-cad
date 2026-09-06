import {
  isRuntimeResolveError,
  type RuntimeResolveError,
} from '@emdash/core/services/runtime-broker/api';
import { err } from '@emdash/shared';
import { runWithTimeout } from '@emdash/shared/scheduling';
import {
  createProvider,
  type CreateProjectProviderDependencies,
} from '@core/features/projects/node/create-project-provider';
import type { ProjectAttachmentAdapter } from '@core/features/projects/node/project-attachment-manager';
import { fileKeyForAbsolutePath, hostPathFromNative } from '@core/primitives/desktop-runtime/api';
import type { Project } from '@core/primitives/projects/api';
import { projectHostRef } from '@core/primitives/projects/api';
import { getProjectById } from './operations/getProjects';

const SSH_PROVIDER_TIMEOUT_MS = 60_000;
const LOCAL_PROVIDER_TIMEOUT_MS = 20_000;

export function createProjectAttachmentAdapter(
  dependencies: CreateProjectProviderDependencies
): ProjectAttachmentAdapter {
  return {
    loadProject: (projectId) => getProjectById(dependencies.db, projectId),
    statRepository: async (project) => {
      const runtime = await dependencies.runtimes.client(projectHostRef(project));
      if (!runtime.success) return err(runtime.error);
      return runtime.data.files.fs.stat(fileKeyForAbsolutePath(hostPathFromNative(project.path)));
    },
    open: (project, signal) => openProvider(dependencies, project, signal),
  };
}

async function openProvider(
  dependencies: CreateProjectProviderDependencies,
  project: Project,
  signal: AbortSignal
) {
  try {
    return await runWithTimeout(() => createProvider(dependencies, project), {
      timeoutMs: project.type === 'ssh' ? SSH_PROVIDER_TIMEOUT_MS : LOCAL_PROVIDER_TIMEOUT_MS,
      signal,
    });
  } catch (error) {
    return err(toProviderOpenError(error));
  }
}

function toProviderOpenError(
  error: unknown
): RuntimeResolveError | { type: 'error'; message: string } {
  if (isRuntimeResolveError(error)) return error;
  return {
    type: 'error',
    message: error instanceof Error ? error.message : String(error),
  };
}
