import type { Result } from '@emdash/shared';
import { type Contract, type ContractImpl } from '@emdash/wire/rpc';
import { and, eq, isNull } from 'drizzle-orm';
import { PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE } from '@core/features/projects/api/attachments';
import type {
  workspacesWireContract,
  WorkspaceError,
  WorkspaceProvisionResult,
  WorkspaceSliceError,
} from '@core/features/workspaces/api';
import { isWorkspacesRuntimeResolveError } from '@core/features/workspaces/api/runtime-adapter';
import type { AppDb } from '@core/services/app-db/node/db';
import { tasks } from '@core/services/app-db/node/schema';
import type { WorkspaceMutationOperations } from './workspace-mutation-service';

type ContractDefinitionsOf<TContract> = TContract extends Contract<infer Defs> ? Defs : never;
type WorkspacesWireImpl = ContractImpl<ContractDefinitionsOf<typeof workspacesWireContract>>;

export type WorkspacesWireTaskProvisioner = (
  taskId: string,
  signal?: AbortSignal
) => Promise<Result<WorkspaceProvisionResult, WorkspaceSliceError>>;

export type CreateWorkspacesWireControllerOptions = {
  db: AppDb;
  mutations: WorkspaceMutationOperations;
  provisionTask: WorkspacesWireTaskProvisioner;
  reprovisionWorkspace(
    workspaceId: string,
    options?: { removeFirst?: boolean }
  ): Promise<Result<Record<string, never>, { type: string; message: string }>>;
};

export type WorkspacesWireController = {
  impl: WorkspacesWireImpl;
  dispose(): Promise<void>;
};

export function createWorkspacesWireController(
  options: CreateWorkspacesWireControllerOptions
): WorkspacesWireController {
  return {
    impl: {
      provision: {
        run: (input, ctx) => runProvisionJob(options, input, ctx.signal),
        toError: unknownToWorkspaceError,
      },
      reprovision: (input) => options.reprovisionWorkspace(input.workspaceId),
      removeAndReprovision: (input) =>
        options.reprovisionWorkspace(input.workspaceId, { removeFirst: true }),
      delete: (input) => options.mutations.delete(input),
      archive: (input) => options.mutations.archive(input),
    },
    async dispose() {},
  };
}

async function runProvisionJob(
  options: CreateWorkspacesWireControllerOptions,
  input: { workspaceId: string; taskId?: string },
  signal?: AbortSignal
): Promise<Result<WorkspaceProvisionResult, WorkspaceSliceError>> {
  const taskId = input.taskId ?? (await resolveTaskIdForWorkspace(options.db, input.workspaceId));
  if (!taskId) {
    return {
      success: false,
      error: workspaceError('missing-task', `No task is linked to workspace ${input.workspaceId}`),
    };
  }
  return options.provisionTask(taskId, signal);
}

async function resolveTaskIdForWorkspace(
  db: AppDb,
  workspaceId: string
): Promise<string | undefined> {
  const [row] = await db
    .select({ id: tasks.id })
    .from(tasks)
    .where(and(eq(tasks.workspaceId, workspaceId), isNull(tasks.deletedAt)))
    .limit(1);
  return row?.id;
}

function workspaceError(type: string, message: string): WorkspaceError {
  return { type, message };
}

function unknownToWorkspaceError(error: unknown): WorkspaceSliceError {
  if (isWorkspacesRuntimeResolveError(error)) return error;
  if (
    typeof error === 'object' &&
    error !== null &&
    typeof (error as { type?: unknown }).type === 'string' &&
    typeof (error as { message?: unknown }).message === 'string'
  ) {
    return error as WorkspaceError;
  }
  return workspaceError(
    'workspace-wire-error',
    error instanceof Error ? error.message : String(error)
  );
}

export function provisionWorkspaceErrorToWorkspaceError(error: unknown): WorkspaceSliceError {
  if (isWorkspacesRuntimeResolveError(error)) return error;
  if (typeof error !== 'object' || error === null) {
    return workspaceError('workspace-provision-failed', String(error));
  }
  const type = (error as { type?: unknown }).type;
  if (type === 'no-intent') return workspaceError('no-intent', 'Workspace has no setup intent');
  if (type === 'missing-workspace') {
    return workspaceError('missing-workspace', 'Workspace row is missing');
  }
  if (type === 'project-missing') {
    return workspaceError('project-missing', 'Project was not found');
  }
  if (type === 'project-unavailable') {
    const unavailable = error as { message?: unknown };
    return workspaceError(
      'project-unavailable',
      typeof unavailable.message === 'string'
        ? unavailable.message
        : PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE
    );
  }
  if (type === 'cancelled') {
    const cancelled = error as { message?: unknown };
    return workspaceError(
      'cancelled',
      typeof cancelled.message === 'string' ? cancelled.message : 'Workspace setup was cancelled'
    );
  }
  if (type === 'setup-failed') {
    const setupError = error as { stepKind?: unknown; stepErrorType?: unknown; message?: unknown };
    return {
      type: 'setup-failed',
      stageId: typeof setupError.stepKind === 'string' ? setupError.stepKind : undefined,
      message:
        typeof setupError.message === 'string'
          ? setupError.message
          : `Workspace setup failed during ${String(setupError.stepKind ?? 'unknown step')}`,
      resolutions:
        typeof setupError.stepErrorType === 'string' ? [setupError.stepErrorType] : undefined,
    };
  }
  return unknownToWorkspaceError(error);
}
