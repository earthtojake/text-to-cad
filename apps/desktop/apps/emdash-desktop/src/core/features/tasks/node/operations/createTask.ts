import crypto from 'node:crypto';
import type { HostRef } from '@emdash/core/primitives/host/api';
import type { CreateConversationInput } from '@emdash/core/runtimes/conversations/api';
import { compileWorktreePayload } from '@emdash/core/runtimes/workspace-registry/api';
import { err, ok, type Result } from '@emdash/shared';
import { and, eq, isNull, sql } from 'drizzle-orm';
import { conversationWireEvents } from '@core/features/conversations/api/node';
import {
  buildHostConversationCreateInput,
  compensateHostConversationRecord,
  conversationIdRegimeFor,
  createHostConversationRecord,
} from '@core/features/conversations/api/node/host-index';
import {
  createConversationRegistry,
  type ConversationRegistry,
} from '@core/features/conversations/api/node/registry';
import { mapConversationRowToConversation } from '@core/features/conversations/api/node/utils';
import type { ConversationsRuntimeBroker } from '@core/features/conversations/api/runtime-adapter';
import {
  PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE,
  type ProjectAttachmentError,
} from '@core/features/projects/api';
import type { ProjectAttachmentManager } from '@core/features/projects/api/node/project-attachment-manager';
import type { ProjectProvider } from '@core/features/projects/api/node/project-provider';
import { mapTaskRowToTask } from '@core/features/tasks/api/node/utils/utils';
import type { WorkspacePlacementResolver } from '@core/features/workspaces/api/node/placement/workspace-placement-resolver';
import { resolveProjectWorkspaceTarget } from '@core/features/workspaces/api/node/project-workspace-target';
import {
  createWorkspaceRegistry,
  type WorkspaceRegistry,
} from '@core/features/workspaces/api/node/registry';
import {
  createWorktreeThroughRegistry,
  type RegistryWorktreeSpec,
  type WorkspaceCreations,
} from '@core/features/workspaces/api/node/registry-verbs';
import {
  findWorkspaceTombstoneConflict,
  type WorkspaceTombstoneConflict,
} from '@core/features/workspaces/api/node/registry/workspace-tombstones';
import type { ConversationConfig } from '@core/primitives/conversations/api';
import type { Conversation } from '@core/primitives/conversations/api';
import type {
  CreateTaskError,
  CreateTaskParams,
  CreateTaskSuccess,
  TaskLifecycleStatus,
} from '@core/primitives/tasks/api';
import { compileWorktreeGitPlan, type WorktreeGitPlan } from '@core/primitives/workspaces/api';
import type { AppDb, DrizzleTx } from '@core/services/app-db/node/db';
import { appDbPokes } from '@core/services/app-db/node/pokes';
import { projects, tasks } from '@core/services/app-db/node/schema';
import type {
  ConversationInsert,
  ConversationRow,
  TaskRow,
  WorkspaceInsert,
} from '@core/services/app-db/node/schema';

type ConvInsert = ConversationInsert;

export interface PreparedCreateTask {
  params: CreateTaskParams;
  initialStatus: TaskLifecycleStatus;
  host: HostRef;
  workspaceId: string;
  newWorkspaceValues: WorkspaceInsert | null;
  registryCreate?: RegistryWorktreeSpec;
  convInsert: ConvInsert | undefined;
  hostConversationInput: CreateConversationInput | undefined;
}

/**
 * Performs all async preparation for creating a task (project validation, workspace
 * resolution). Returns a `PreparedCreateTask` that can be committed synchronously
 * inside a Drizzle transaction via `commitCreateTask`.
 */
export async function prepareCreateTask(
  db: AppDb,
  projectSessions: Pick<ProjectAttachmentManager, 'requireAttached'>,
  placement: Pick<WorkspacePlacementResolver, 'resolveWorktreeRoot'>,
  params: CreateTaskParams
): Promise<Result<PreparedCreateTask, CreateTaskError>> {
  const attached = projectSessions.requireAttached(params.projectId);
  if (!attached.success && attached.error.type === 'project-missing') {
    return err({ type: 'project-not-found' });
  }
  if (!attached.success) return err(projectUnavailable(attached.error));
  const project = attached.data;

  const { workspaceConfig } = params;
  const initialStatus: TaskLifecycleStatus = params.taskConfig.initialStatus ?? 'in_progress';

  let workspaceId: string;
  let newWorkspaceValues: WorkspaceInsert | null = null;
  let registryCreate: RegistryWorktreeSpec | undefined;

  const wsTarget = workspaceConfig.workspace;
  // The full worktree git plan (branch, baseRef?, publish, gitSetup?), compiled once
  // desktop-side; PR presets carry their fetch/upstream/breadcrumb instructions here.
  // Base and push remotes come from one blessed-resolver snapshot (spec:
  // github-git-settings §2); plans refuse any requested operation whose target
  // remote cannot be resolved.
  let gitPlan: WorktreeGitPlan | undefined;
  if (workspaceConfig.git.kind !== 'none') {
    const { baseRemote, pushRemote } = await project.gitRepository.getEffectiveRemotes();
    if (baseRemote === null && workspaceConfig.git.kind === 'pr-branch') {
      return err({
        type: 'provision-failed',
        message: 'The repository has no git remotes, so a pull request cannot be checked out.',
      });
    }
    try {
      gitPlan = compileWorktreeGitPlan(workspaceConfig.git, { baseRemote, pushRemote });
    } catch (error) {
      return err({
        type: 'provision-failed',
        message: error instanceof Error ? error.message : String(error),
      });
    }
  }
  const branchName = gitPlan?.branch;
  // Tombstone-aware creation admission (ADR 0006, spec §4): a pending deletion
  // tombstone on the target workspace or its branch refuses creation — a data check
  // against the mirror, the successor to the retired claim-conflict preflight.
  // Recreating waits for sweep convergence or the user's untrack. The requested
  // worktree path gets the symmetric check inside the allocator below, which refuses
  // tombstone-pending paths instead of suffixing past them.
  const isRemoteHost = project.host.type === 'remote';
  const tombstoneConflict = findWorkspaceTombstoneConflict(
    db,
    wsTarget.kind === 'repository-instance'
      ? { kind: 'workspace', workspaceId: wsTarget.workspaceId }
      : {
          kind: 'placement',
          location: isRemoteHost ? 'remote' : 'local',
          sshConnectionId: isRemoteHost ? project.host.id : null,
          branch: branchName ?? undefined,
        }
  );
  if (tombstoneConflict) {
    return err(tombstoneConflict);
  }

  let conversationWorkspacePath: string | null = null;
  if (wsTarget.kind === 'repository-instance') {
    const target = await resolveProjectWorkspaceTarget(
      db,
      {
        id: project.project.id,
        repositoryWorkspaceId: project.project.repositoryWorkspaceId,
        host: project.host,
      },
      wsTarget.workspaceId
    );
    if (!target.success) return err(target.error);
    workspaceId = target.data.id;
    conversationWorkspacePath = target.data.path;
  } else {
    // 'new-worktree' — derive location from the project.
    workspaceId = crypto.randomUUID();

    const [projectRow] = await db
      .select({ repositoryWorkspaceId: projects.repositoryWorkspaceId })
      .from(projects)
      .where(and(eq(projects.id, params.projectId), isNull(projects.deletedAt)))
      .limit(1);

    const repositoryWorkspaceId = projectRow?.repositoryWorkspaceId;
    if (!repositoryWorkspaceId) {
      return err({
        type: 'provision-failed',
        message: 'The project repository workspace was not found.',
      });
    }
    const preservePatterns = await resolveProjectPreservePatterns(project, repositoryWorkspaceId);
    if (preservePatterns === null) {
      return err({
        type: 'provision-failed',
        message: 'The project configuration could not be resolved.',
      });
    }

    const isRemote = project.host.type === 'remote';
    const location = isRemote ? 'remote' : 'local';
    const sshConnectionId = isRemote ? project.host.id : null;
    const legacyType = isRemote ? 'project-ssh' : 'local';

    if (!gitPlan || !branchName) {
      return err({
        type: 'provision-failed',
        message: 'A Git branch is required when creating a worktree.',
      });
    }
    const root = await placement.resolveWorktreeRoot(project.project);
    if (!root.success) {
      return err({
        type: 'provision-failed',
        message: root.error.message,
      });
    }
    const compiled = compileWorktreePayload({
      repoPath: project.repoPath,
      worktreeRoot: root.data,
      branchName,
      preservePatterns,
    });
    const registry = createWorkspaceRegistry(db);
    const allocated = allocateRegistryPath(
      db,
      registry,
      location,
      sshConnectionId,
      compiled.worktreePath
    );
    if (!allocated.success) return allocated;
    const workspacePath = allocated.data;
    conversationWorkspacePath = workspacePath;

    newWorkspaceValues = {
      id: workspaceId,
      kind: 'worktree',
      location,
      sshConnectionId,
      parentId: repositoryWorkspaceId,
      type: legacyType,
      origin: 'registered',
      config: workspaceConfig,
      path: workspacePath,
    };
    registryCreate = {
      host: project.host,
      repositoryWorkspaceId,
      repositoryPath: project.repoPath,
      workspaceId,
      branch: gitPlan.branch,
      ...(gitPlan.baseRef !== undefined && { baseRef: gitPlan.baseRef }),
      path: workspacePath,
      preservePatterns: compiled.preservePatterns,
      ...(gitPlan.publish !== undefined && { publish: gitPlan.publish }),
      ...(gitPlan.gitSetup !== undefined && { gitSetup: gitPlan.gitSetup }),
    };
  }

  let convInsert: ConvInsert | undefined;
  let hostConversationInput: CreateConversationInput | undefined;
  if (params.taskConfig.initialConversation) {
    const ic = params.taskConfig.initialConversation;
    const conversationType = ic.type ?? 'pty';
    const initialQueue = ic.initialQueue?.filter((prompt) => prompt.text.trim());
    const configObj: ConversationConfig =
      conversationType === 'acp'
        ? {
            version: '1',
            type: 'acp',
            ...(ic.autoApprove !== undefined && { autoApprove: ic.autoApprove }),
            ...(initialQueue?.length && { initialQueue }),
            ...(ic.model && { model: ic.model }),
          }
        : {
            version: '1',
            type: 'pty',
            ...(ic.autoApprove !== undefined && { autoApprove: ic.autoApprove }),
            ...(ic.initialPrompt?.trim() && { initialPrompt: ic.initialPrompt.trim() }),
            ...(ic.model && { model: ic.model }),
          };
    if (conversationWorkspacePath === null) {
      return err({
        type: 'provision-failed',
        message: 'The target workspace has no path to freeze into the conversation record.',
      });
    }
    const isRemote = project.host.type === 'remote';
    convInsert = {
      id: ic.id,
      projectId: params.projectId,
      taskId: params.id,
      title: ic.title ?? '',
      provider: ic.provider,
      config: configObj,
      isInitialConversation: true,
      lastSessionActivityAt: new Date().toISOString(),
      type: conversationType,
      // Frozen at creation (spec §6.1): the record's paths are set before the
      // worktree exists; sessions run in the workspace root, so cwd matches.
      cwd: conversationWorkspacePath,
      workspacePath: conversationWorkspacePath,
      idRegime: conversationIdRegimeFor(conversationType),
      location: isRemote ? 'remote' : 'local',
      sshConnectionId: isRemote ? project.host.id : null,
    };
    hostConversationInput = buildHostConversationCreateInput({
      id: ic.id,
      provider: ic.provider,
      type: conversationType,
      title: ic.title ?? '',
      workspacePath: conversationWorkspacePath,
      config: configObj,
      createdAt: Date.now(),
    });
  }

  return ok({
    params,
    initialStatus,
    host: project.host,
    workspaceId,
    newWorkspaceValues,
    registryCreate,
    convInsert,
    hostConversationInput,
  });
}

export async function resolveProjectPreservePatterns(
  project: Pick<ProjectProvider, 'workspaceRegistry'>,
  repositoryWorkspaceId: string
): Promise<string[] | null> {
  const config = await project.workspaceRegistry.getProjectConfig({
    workspaceId: repositoryWorkspaceId,
  });
  return config.success ? config.data.resolved.preservePatterns.value : null;
}

/**
 * Synchronously runs the task/workspace/conversation inserts within the provided
 * transaction. Must be called with a `PreparedCreateTask` from `prepareCreateTask`.
 * Returns the raw DB rows; call `finalizeCreateTask` after the transaction commits
 * to build the result and emit side-effect events.
 */
export function commitCreateTask(
  prepared: PreparedCreateTask,
  tx: DrizzleTx,
  registry: WorkspaceRegistry,
  conversationRegistry: ConversationRegistry
): { taskRow: TaskRow; convRow: ConversationRow | undefined } {
  const { params, initialStatus, workspaceId, newWorkspaceValues, convInsert } = prepared;

  const [taskRow] = tx
    .insert(tasks)
    .values({
      id: params.id,
      projectId: params.projectId,
      name: params.taskConfig.name,
      status: initialStatus,
      workspaceId,
      linkedIssue: params.taskConfig.linkedIssue ?? null,
      type: 'task',
      updatedAt: sql`CURRENT_TIMESTAMP`,
      statusChangedAt: sql`CURRENT_TIMESTAMP`,
      lastInteractedAt: sql`CURRENT_TIMESTAMP`,
    })
    .returning()
    .all();

  if (newWorkspaceValues) {
    registry.recordCreationIntent(newWorkspaceValues, tx);
  }

  let convRow: ConversationRow | undefined;
  if (convInsert) {
    convRow = conversationRegistry.register(convInsert, tx);
  }

  return { taskRow, convRow };
}

/**
 * Builds the `CreateTaskSuccess` result and emits post-commit side-effect events.
 * Call this after the transaction that ran `commitCreateTask` has committed.
 */
export function finalizeCreateTask(
  prepared: PreparedCreateTask,
  taskRow: TaskRow,
  convRow: ConversationRow | undefined
): CreateTaskSuccess {
  const task = mapTaskRowToTask(taskRow);

  let initialConversation: Conversation | undefined;
  if (convRow) {
    initialConversation = mapConversationRowToConversation(convRow) ?? undefined;
    if (initialConversation) {
      conversationWireEvents.emit(undefined, {
        type: 'created',
        conversation: initialConversation,
      });
      appDbPokes.conversations.poke({
        projectId: prepared.params.projectId,
        taskId: prepared.params.id,
      });
    }
  }

  appDbPokes.tasks.poke({ projectId: prepared.params.projectId, taskId: prepared.params.id });
  if (prepared.newWorkspaceValues) {
    appDbPokes.workspaces.poke({
      projectId: prepared.params.projectId,
      taskId: prepared.params.id,
      workspaceId: prepared.workspaceId,
    });
  }
  return { task: { ...task, workspaceId: prepared.workspaceId }, initialConversation };
}

export async function createTask(
  db: AppDb,
  projects: Pick<ProjectAttachmentManager, 'requireAttached'>,
  placement: Pick<WorkspacePlacementResolver, 'resolveWorktreeRoot'>,
  runtimes: ConversationsRuntimeBroker,
  creations: WorkspaceCreations,
  params: CreateTaskParams
): Promise<Result<CreateTaskSuccess, CreateTaskError>> {
  const prepared = await prepareCreateTask(db, projects, placement, params);
  if (!prepared.success) return prepared;

  // Host-first ordering (spec §6.2): the index is authoritative for conversation
  // existence, so the record must exist — dangling — before the desktop transaction
  // links to it. Live sync may adopt it first; register atomically claims that mirror row.
  // The host is reachable by construction (gate in prepare).
  const hostInput = prepared.data.hostConversationInput;
  if (hostInput) {
    const registered = await createHostConversationRecord(runtimes, prepared.data.host, hostInput);
    if (!registered.success) {
      return err({ type: 'provision-failed', message: registered.message });
    }
  }

  let taskRow!: TaskRow;
  let convRow: ConversationRow | undefined;
  const registry = createWorkspaceRegistry(db);
  const conversationRegistry = createConversationRegistry(db);
  try {
    db.transaction((tx) => {
      ({ taskRow, convRow } = commitCreateTask(prepared.data, tx, registry, conversationRegistry));
    });
  } catch (error) {
    if (hostInput) {
      await compensateHostConversationRecord(
        runtimes,
        prepared.data.host,
        hostInput.conversationId
      );
    }
    throw error;
  }

  // The worktree is created through the plain registry verb (ADR 0005), in the
  // background: progress and the durable outcome surface through the records live
  // model and the mirror. Provisioning awaits the pending creation; a failure shows
  // its stage on the task and a retry replays the identical spec.
  const registryCreate = prepared.data.registryCreate;
  if (registryCreate) {
    void creations.run(registryCreate.workspaceId, () =>
      createWorktreeThroughRegistry(runtimes, registryCreate)
    );
  }

  return ok(finalizeCreateTask(prepared.data, taskRow, convRow));
}

function projectUnavailable(
  error: ProjectAttachmentError
): Extract<CreateTaskError, { type: 'project-unavailable' }> {
  return {
    type: 'project-unavailable',
    reason: error.type,
    message: PROJECT_LIVE_ACCESS_REQUIRED_MESSAGE,
  };
}

/**
 * Picks the first free registry path, suffixing past genuine live-row collisions
 * (`path-2`, `path-3`, …). A candidate held by a pending deletion tombstone refuses
 * instead (ADR 0006, spec §4): recreating there waits for sweep convergence or the
 * user's Untrack-anyway — never a silent rename around the hold.
 */
function allocateRegistryPath(
  db: AppDb,
  registry: WorkspaceRegistry,
  location: NonNullable<WorkspaceInsert['location']>,
  sshConnectionId: string | null,
  basePath: string
): Result<string, WorkspaceTombstoneConflict> {
  for (let suffix = 1; ; suffix += 1) {
    const candidate = suffix === 1 ? basePath : `${basePath}-${suffix}`;
    const tombstoned = findWorkspaceTombstoneConflict(db, {
      kind: 'placement',
      location,
      sshConnectionId,
      path: candidate,
    });
    if (tombstoned) return err(tombstoned);
    if (!registry.findLiveByPath(location, sshConnectionId, candidate)) return ok(candidate);
  }
}
