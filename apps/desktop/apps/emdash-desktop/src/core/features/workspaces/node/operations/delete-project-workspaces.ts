import type { TaskService } from '@core/features/tasks/api/node/task-service';
import {
  deleteWorkspacePathThroughRegistry,
  type WorkspaceRemovalBroker,
} from '@core/features/workspaces/api/node/operations/workspace-removal';
import type {
  ProjectWorkspaceActionResult,
  ProjectWorkspaceActionSummary,
  ProjectWorkspaceRow,
} from '@core/primitives/workspaces/api';
import type { AppDb } from '@core/services/app-db/node/db';
import {
  getProjectWorkspaceProject,
  listProjectWorkspaces,
  type ListProjectWorkspacesDependencies,
} from './list-project-workspaces';

export async function deleteProjectWorkspaces(
  dependencies: ListProjectWorkspacesDependencies & {
    taskService: Pick<TaskService, 'deleteTask'>;
  },
  input: {
    projectId: string;
    paths: string[];
    /** Opt-in (spec §7.1): delete the workspaces' conversation records on the host too. */
    deleteConversations?: boolean;
  }
): Promise<ProjectWorkspaceActionSummary> {
  if (input.paths.length === 0) return { succeededCount: 0, failedCount: 0, results: [] };

  const project = await getProjectWorkspaceProject(dependencies.db, input.projectId);
  const rows = await listProjectWorkspaces(dependencies, input.projectId);
  const rowsByPath = new Map(rows.rows.map((row) => [row.path, row]));
  const results: ProjectWorkspaceActionResult[] = [];

  for (const targetPath of input.paths) {
    const row = rowsByPath.get(targetPath);
    if (!row) {
      results.push({
        path: targetPath,
        success: false,
        reason: 'workspace-not-found',
        message: 'Workspace was not found.',
      });
      continue;
    }
    const result = await deleteProjectWorkspaceRow(
      dependencies,
      input.projectId,
      project.path,
      row,
      { deleteConversations: input.deleteConversations ?? false }
    );
    results.push(result);
  }

  const succeededCount = results.filter((result) => result.success).length;
  return {
    succeededCount,
    failedCount: results.length - succeededCount,
    results,
  };
}

async function deleteProjectWorkspaceRow(
  dependencies: {
    db: AppDb;
    runtimes: WorkspaceRemovalBroker;
    taskService: Pick<TaskService, 'deleteTask'>;
  },
  projectId: string,
  projectPath: string,
  row: ProjectWorkspaceRow,
  options: { deleteConversations: boolean }
): Promise<ProjectWorkspaceActionResult> {
  if (row.kind === 'root') {
    return {
      path: row.path,
      workspaceId: row.workspaceId ?? undefined,
      success: false,
      reason: 'root-refused',
      message: 'Repository root cannot be deleted.',
    };
  }

  if (!row.canDelete) {
    return {
      path: row.path,
      workspaceId: row.workspaceId ?? undefined,
      success: false,
      reason: 'unsupported-workspace',
      message: 'This workspace does not support deletion.',
    };
  }

  try {
    if (row.tasks.length > 0) {
      for (const task of row.tasks) {
        await dependencies.taskService.deleteTask(projectId, task.taskId, {
          deleteWorktree: true,
          deleteBranch: false,
          // The workspace-removal dialog's choice is the visible intent here; the
          // task-deletion default (delete) does not apply.
          deleteConversations: options.deleteConversations,
        });
      }
      return success(row);
    }

    if (row.pathState === 'missing' && !row.workspaceId) {
      return success(row);
    }

    const result = await deleteWorkspacePathThroughRegistry(
      dependencies.db,
      dependencies.runtimes,
      {
        projectId,
        workspaceId: row.workspaceId ?? undefined,
        workspacePath: row.path,
        branchName: row.branch ?? undefined,
      },
      { deleteConversations: options.deleteConversations }
    );
    if (!result.success) {
      return {
        path: row.path,
        workspaceId: row.workspaceId ?? undefined,
        success: false,
        reason: 'delete-failed',
        message: result.error.message,
      };
    }
    return success(row);
  } catch (error) {
    return {
      path: row.path,
      workspaceId: row.workspaceId ?? undefined,
      success: false,
      reason: 'delete-failed',
      message: error instanceof Error ? error.message : String(error),
    };
  }
}

function success(row: ProjectWorkspaceRow): ProjectWorkspaceActionResult {
  return {
    path: row.path,
    workspaceId: row.workspaceId ?? undefined,
    success: true,
    reclaimedBytes: row.usage?.totalBytes,
  };
}
