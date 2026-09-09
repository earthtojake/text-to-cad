import { localBranchRefSchema } from '@emdash/core/runtimes/git/api';
import { and, eq, isNull } from 'drizzle-orm';
import type { ProjectProvider } from '@core/features/projects/api/node/project-provider';
import {
  liveWorkspaces,
  workspaceRegistryTable as workspacesTable,
} from '@core/features/workspaces/api/node/registry';
import { getProvisionedWorkspaceBranch } from '@core/features/workspaces/api/node/workspace-branch';
import type { WorkspaceIdentityService } from '@core/features/workspaces/api/node/workspace-identity-service';
import type {
  ProjectSettingsWriteTarget,
  ProjectSettingsWriteTargetOption,
  WriteProjectConfigRequest,
} from '@core/primitives/project-settings/api';
import type { WorkspaceConfig, WorkspaceKind } from '@core/primitives/workspaces/api';
import type { AppDb } from '@core/services/app-db/node/db';
import { projects as projectsTable, tasks as tasksTable } from '@core/services/app-db/node/schema';
import { filesClientScope, type FilesClientScope } from '@core/services/runtime-broker/node/files';

export type ProjectSettingsResolvedTarget = ProjectSettingsWriteTargetOption & {
  files: FilesClientScope;
  configPath: string;
};

function stripTarget(target: ProjectSettingsWriteTargetOption): ProjectSettingsWriteTarget {
  if (target.type === 'project') return { type: 'project' };
  if (target.type === 'task') return { type: 'task', taskId: target.taskId };
  return { type: 'workspace', workspaceId: target.workspaceId };
}

export function stripResolvedTarget(
  target: ProjectSettingsResolvedTarget
): ProjectSettingsWriteTargetOption {
  const { files: _files, ...option } = target;
  return option;
}

function targetKey(target: ProjectSettingsWriteTarget): string {
  if (target.type === 'project') return 'project';
  if (target.type === 'task') return `task:${target.taskId}`;
  return `workspace:${target.workspaceId}`;
}

type TaskTargetRow = {
  id: string;
  name: string;
  workspaceId: string | null;
  workspaceKind: WorkspaceKind | null;
  workspaceConfig: WorkspaceConfig | null;
};

async function resolveTaskTarget(
  workspaceIdentity: WorkspaceIdentityService,
  project: ProjectProvider,
  task: TaskTargetRow
): Promise<ProjectSettingsResolvedTarget | null> {
  let targetPath: string | null = null;
  let files: FilesClientScope | null = null;
  let configPath: string | null = null;

  if (task.workspaceId) {
    const identity = await workspaceIdentity.resolve(task.workspaceId);
    if (identity) {
      targetPath = identity.path;
      files = filesClientScope(project.files.client, identity.path);
      configPath = project.configPathForDirectory(identity.path);
    }
  }

  const provisionedBranch = getProvisionedWorkspaceBranch({
    kind: task.workspaceKind,
    config: task.workspaceConfig,
  });
  if (!targetPath && provisionedBranch) {
    targetPath = await project.findTaskWorktree(
      localBranchRefSchema.parse(`refs/heads/${provisionedBranch}`)
    );
  }
  if (!targetPath) return null;
  if (targetPath === project.repoPath) return null;
  const resolvedFiles = files ?? project.files;

  return {
    type: 'task',
    taskId: task.id,
    label: task.name,
    path: targetPath,
    ...(task.workspaceId ? { sourceWorkspaceId: task.workspaceId } : {}),
    files: resolvedFiles,
    configPath: configPath ?? project.configPathForDirectory(targetPath),
  };
}

export async function resolveAllProjectSettingsTargets(
  db: AppDb,
  workspaceIdentity: WorkspaceIdentityService,
  project: ProjectProvider
): Promise<ProjectSettingsResolvedTarget[]> {
  const [projectRow] = await db
    .select({ name: projectsTable.name })
    .from(projectsTable)
    .where(and(eq(projectsTable.id, project.projectId), isNull(projectsTable.deletedAt)))
    .limit(1);

  const projectTarget: ProjectSettingsResolvedTarget = {
    type: 'project',
    label: projectRow?.name ?? 'Project repository',
    path: project.repoPath,
    files: project.files,
    configPath: project.projectConfigPath,
    ...(project.project?.repositoryWorkspaceId
      ? { sourceWorkspaceId: project.project.repositoryWorkspaceId }
      : {}),
  };
  if (!projectRow) return [projectTarget];

  const taskRows = await db
    .select({
      id: tasksTable.id,
      name: tasksTable.name,
      workspaceId: tasksTable.workspaceId,
      workspaceKind: workspacesTable.kind,
      workspaceConfig: workspacesTable.config,
    })
    .from(tasksTable)
    .leftJoin(
      workspacesTable,
      and(eq(tasksTable.workspaceId, workspacesTable.id), liveWorkspaces())
    )
    .where(and(eq(tasksTable.projectId, project.projectId), isNull(tasksTable.deletedAt)));

  const taskTargets = (
    await Promise.all(taskRows.map((task) => resolveTaskTarget(workspaceIdentity, project, task)))
  ).filter((target): target is ProjectSettingsResolvedTarget => target !== null);

  return [projectTarget, ...taskTargets];
}

export function getProjectSettingsWriteTargets(
  targets: ProjectSettingsResolvedTarget[]
): ProjectSettingsWriteTargetOption[] {
  return targets.map(stripResolvedTarget);
}

export async function resolveProjectSettingsTarget(
  workspaceIdentity: WorkspaceIdentityService,
  project: ProjectProvider,
  request: Pick<WriteProjectConfigRequest, 'target'>,
  resolvedTargets: ProjectSettingsResolvedTarget[]
): Promise<ProjectSettingsResolvedTarget | null> {
  const target = resolvedTargets.find(
    (candidate) => targetKey(stripTarget(candidate)) === targetKey(request.target)
  );
  if (target) return target;

  if (request.target.type === 'workspace') {
    const workspace = await workspaceIdentity.resolve(request.target.workspaceId);
    if (!workspace || workspace.projectId !== project.projectId) return null;
    return {
      type: 'workspace',
      workspaceId: request.target.workspaceId,
      label: 'Workspace',
      path: workspace.path,
      sourceWorkspaceId: request.target.workspaceId,
      files: filesClientScope(project.files.client, workspace.path),
      configPath: project.configPathForDirectory(workspace.path),
    };
  }

  return null;
}
