import { randomUUID } from 'node:crypto';
import type { HostRef } from '@emdash/core/primitives/host/api';
import { hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import type { RuntimeBroker } from '@emdash/core/services/runtime-broker/api';
import { err, ok } from '@emdash/shared';
import { projectEvents } from '@core/features/projects/api/node/project-events';
import { fileKeyForAbsolutePath, hostPathFromNative } from '@core/primitives/desktop-runtime/api';
import type { CreateProjectResult } from '@core/primitives/projects/api';
import type {
  CreateProjectParams,
  InspectProjectPathParams,
  ProjectPathInspection,
} from '@core/primitives/projects/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { fsErrorMessage } from '@core/services/runtime-broker/node/files';
import { ensureProjectRepository } from './create-project-utils';
import { projectFromRow } from './getProjects';
import { getProjectByPath } from './getProjects';
import { getProjectPathStatus } from './project-path-status';
import { registerRepositoryWorkspace } from './register-repository-workspace';

export type CreateProjectOnHostParams = {
  id?: string;
  path: string;
  name: string;
  initGitRepository?: boolean;
};

export type CreateProjectDependencies = {
  db: AppDb;
  runtimes: Pick<RuntimeBroker, 'client'>;
};

export async function createProject(
  dependencies: CreateProjectDependencies,
  params: CreateProjectParams
): Promise<CreateProjectResult> {
  const host = params.type === 'ssh' ? hostRef('remote', params.connectionId) : LOCAL_HOST_REF;
  return createProjectOnHost(dependencies, host, {
    id: params.id,
    name: params.name,
    path: params.path,
    initGitRepository: params.initGitRepository,
  });
}

export async function inspectProjectPath(
  dependencies: CreateProjectDependencies,
  params: InspectProjectPathParams
): Promise<ProjectPathInspection> {
  const host = params.type === 'ssh' ? hostRef('remote', params.connectionId) : LOCAL_HOST_REF;
  const [status, existingProject] = await Promise.all([
    getProjectPathStatus(dependencies, host, params.path),
    getProjectByPath(dependencies.db, host, params.path),
  ]);
  return { ...status, existingProject };
}

async function createProjectOnHost(
  dependencies: CreateProjectDependencies,
  host: HostRef,
  params: CreateProjectOnHostParams
): Promise<CreateProjectResult> {
  const runtime = await dependencies.runtimes.client(host);
  if (!runtime.success) return err(runtime.error);

  const pathEntry = await runtime.data.files.fs.stat(
    fileKeyForAbsolutePath(hostPathFromNative(params.path))
  );
  if (!pathEntry.success && pathEntry.error.type !== 'not-found') {
    return err({
      type: 'inspect-failed',
      path: params.path,
      message: fsErrorMessage(pathEntry.error),
    });
  }
  if (!pathEntry.success || pathEntry.data.type !== 'directory') {
    return err({
      type: 'invalid-directory',
      path: params.path,
      message: 'Invalid directory',
    });
  }

  const repositoryResult = await ensureProjectRepository(
    runtime.data.git,
    params.path,
    params.initGitRepository
  );
  if (
    !repositoryResult.success &&
    (repositoryResult.error.type !== 'not-repository' || params.initGitRepository)
  ) {
    return repositoryResult;
  }

  const gitInfo = repositoryResult.success
    ? repositoryResult.data
    : {
        rootPath: params.path,
        baseRef: null,
      };

  const proposedWorkspaceId = randomUUID();
  const registered = await runtime.data.workspaceRegistry.createWorkspace({
    workspaceId: proposedWorkspaceId,
    path: gitInfo.rootPath,
  });
  if (!registered.success) {
    return err({
      type: 'invalid-directory',
      path: gitInfo.rootPath,
      message: describeWorkspaceRegistrationError(registered.error),
    });
  }

  const stored = registerRepositoryWorkspace(dependencies.db, {
    project: {
      id: params.id ?? randomUUID(),
      name: params.name,
      baseRef: gitInfo.baseRef,
    },
    host,
    record: registered.data,
  });
  if (!stored.success) {
    return err({
      type: 'invalid-directory',
      path: registered.data.path,
      message:
        stored.error.type === 'project-already-linked'
          ? 'A project already exists at this path'
          : `Could not claim the project repository (${stored.error.type})`,
    });
  }
  const row = stored.data;
  const repositoryWorkspaceId = registered.data.id;

  const project = projectFromRow(row, {
    path: registered.data.path,
    location: host.type === 'remote' ? 'remote' : 'local',
    sshConnectionId: host.type === 'remote' ? host.id : null,
  });
  if (!project) {
    return err({
      type: 'invalid-directory',
      path: gitInfo.rootPath,
      message: 'Project repository path could not be resolved',
    });
  }
  project.repositoryWorkspaceId = repositoryWorkspaceId;

  projectEvents._emit('project:created', project);
  appDbPokes.projects.poke({ projectId: project.id });

  return ok(project);
}

function describeWorkspaceRegistrationError(error: {
  type: string;
  path?: string;
  message?: string;
}): string {
  switch (error.type) {
    case 'path-not-found':
      return `Repository path not found: ${error.path ?? 'unknown path'}`;
    case 'inspect-failed':
    case 'immutable-field-mismatch':
      return error.message ?? `Could not register the project repository (${error.type})`;
    default:
      return `Could not register the project repository (${error.type})`;
  }
}
