import type { GitBranchRef } from '@emdash/core/runtimes/git/api';
import type { RuntimeResolveError } from '@emdash/core/services/runtime-broker/api';
import { ok, type Result } from '@emdash/shared';
import type { ConversationProvider } from '@core/features/conversations/api/node/types';
import type { TaskProvider } from '@core/features/projects/api/node/project-provider';
import type { RepoFactsSource } from '@core/features/projects/api/node/settings/effective-settings';
import type { ProjectSettingsProvider } from '@core/features/projects/api/node/settings/provider';
import type { Workspace } from '@core/features/workspaces/api/node/workspace';
import {
  buildTaskProviders,
  resolveTaskEnv,
  type ResolveTaskEnvError,
  type TaskProviderOpts,
} from '@core/features/workspaces/api/node/workspace-factory';
import type { Task } from '@core/primitives/tasks/api';

export type BuildTaskResult = {
  taskProvider: TaskProvider;
  conversationProvider: ConversationProvider;
};

export async function buildTaskFromWorkspace(
  task: Task,
  workspace: Workspace,
  projectId: string,
  projectPath: string,
  settings: ProjectSettingsProvider,
  repoFacts: RepoFactsSource,
  createConversationProvider: (options: TaskProviderOpts) => ConversationProvider,
  workspaceBranchName?: string,
  workspaceSourceBranch?: GitBranchRef
): Promise<Result<BuildTaskResult, RuntimeResolveError | ResolveTaskEnvError>> {
  const taskEnv = await resolveTaskEnv(task, workspace, projectPath, settings, repoFacts);
  if (!taskEnv.success) return taskEnv;
  const { taskEnvVars, tmuxEnabled, shellSetup } = taskEnv.data;
  const providers = await buildTaskProviders(
    {
      host: workspace.host,
      files: workspace.files,
      tuiAgents: workspace.tuiAgents,
      projectId,
      taskId: task.id,
      workspaceId: workspace.id,
      taskPath: workspace.path,
      tmuxEnabled,
      shellSetup,
      taskEnvVars,
    },
    createConversationProvider
  );
  if (!providers.success) return providers;
  const { conversations: conversationProvider } = providers.data;
  const taskProvider: TaskProvider = {
    taskId: task.id,
    taskBranch: workspaceBranchName,
    sourceBranch: workspaceSourceBranch,
    taskEnvVars,
    conversations: conversationProvider,
  };
  return ok({ taskProvider, conversationProvider });
}
