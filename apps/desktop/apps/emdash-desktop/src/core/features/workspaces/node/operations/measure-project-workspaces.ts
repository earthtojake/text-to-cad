import type { MeasureUsageError } from '@emdash/core/runtimes/workspace-registry/api';
import {
  runtimeResolveErrorAsError,
  type RuntimeBroker,
} from '@emdash/core/services/runtime-broker/api';
import type {
  MeasureProjectWorkspacesInput,
  MeasureProjectWorkspacesResult,
  ProjectWorkspaceRow,
  ProjectWorkspaceUsageResult,
} from '@core/primitives/workspaces/api';
import {
  getProjectWorkspaceProject,
  listProjectWorkspaces,
  mapWithConcurrency,
  projectWorkspaceHost,
  type ListProjectWorkspacesDependencies,
} from './list-project-workspaces';

const MEASURE_CONCURRENCY = 4;

export async function measureProjectWorkspaces(
  dependencies: ListProjectWorkspacesDependencies,
  input: MeasureProjectWorkspacesInput
): Promise<MeasureProjectWorkspacesResult> {
  if (input.paths.length === 0) {
    return { scannedAt: new Date().toISOString(), projectId: input.projectId, results: [] };
  }

  const project = await getProjectWorkspaceProject(dependencies.db, input.projectId);
  const listed = await listProjectWorkspaces(dependencies, input.projectId);
  const rowsByPath = new Map(listed.rows.map((row) => [row.path, row]));
  const results = await mapWithConcurrency(input.paths, MEASURE_CONCURRENCY, async (targetPath) => {
    const row = rowsByPath.get(targetPath);
    if (!row) {
      return {
        path: targetPath,
        success: false,
        message: 'Workspace was not found.',
      } satisfies ProjectWorkspaceUsageResult;
    }
    return await measureRow(dependencies, project, row);
  });

  return {
    scannedAt: new Date().toISOString(),
    projectId: input.projectId,
    results,
  };
}

async function measureRow(
  dependencies: { runtimes: Pick<RuntimeBroker, 'client'> },
  project: Awaited<ReturnType<typeof getProjectWorkspaceProject>>,
  row: ProjectWorkspaceRow
): Promise<ProjectWorkspaceUsageResult> {
  if (row.pathState === 'missing') {
    return { path: row.path, success: false, message: 'Workspace path is missing.' };
  }
  if (row.pathState === 'no-path') {
    return { path: row.path, success: false, message: 'Workspace path is not available.' };
  }
  if (row.workspaceId === null) {
    return { path: row.path, success: false, message: 'Workspace is not registered.' };
  }

  try {
    const host = projectWorkspaceHost(project);
    const runtime = await dependencies.runtimes.client(host);
    if (!runtime.success) throw runtimeResolveErrorAsError(runtime.error);
    const usage = await runtime.data.workspaceRegistry.measureUsage({
      workspaceId: row.workspaceId,
    });
    if (!usage.success) {
      const message = measureUsageErrorMessage(usage.error);
      return {
        path: row.path,
        success: false,
        message,
        errors: [{ path: row.path, message }],
      };
    }
    return {
      path: row.path,
      success: true,
      usage: {
        totalBytes: usage.data.totalBytes,
        artifactBytes: usage.data.artifactBytes,
        errors: usage.data.errors,
      },
    };
  } catch (error) {
    return {
      path: row.path,
      success: false,
      message: error instanceof Error ? error.message : String(error),
    };
  }
}

function measureUsageErrorMessage(error: MeasureUsageError): string {
  return error.type === 'workspace-not-found'
    ? 'Workspace is not registered on the host.'
    : error.message;
}
