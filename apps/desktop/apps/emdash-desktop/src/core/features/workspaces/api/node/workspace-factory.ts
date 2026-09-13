import type { HostRef } from '@emdash/core/primitives/host/api';
import type { RuntimeResolveError } from '@emdash/core/services/runtime-broker/api';
import { err, ok, type Result } from '@emdash/shared';
import type { ConversationProvider } from '@core/features/conversations/api/node/types';
import {
  resolveProjectEffectiveSettings,
  type RepoFactsSource,
} from '@core/features/projects/api/node/settings/effective-settings';
import type { ProjectSettingsProvider } from '@core/features/projects/api/node/settings/provider';
import type { Workspace } from '@core/features/workspaces/api/node/workspace';
import { getTaskEnvVars } from '@core/features/workspaces/api/node/workspace-env';
import type { Task } from '@core/primitives/tasks/api';
import type { TuiAgentsRuntimeClient } from '@core/services/runtime-broker/api/clients';
import type { FilesClientScope } from '@core/services/runtime-broker/node/files';

export type WorkspaceType = { kind: 'local' } | { kind: 'ssh'; connectionId: string };

export type TaskProviderOpts = {
  host: HostRef;
  files: FilesClientScope;
  tuiAgents: TuiAgentsRuntimeClient;
  projectId: string;
  taskId: string;
  workspaceId: string;
  taskPath: string;
  tmuxEnabled: boolean;
  shellSetup?: string;
  taskEnvVars: Record<string, string>;
};

export type ResolveTaskEnvError = {
  type: 'setup-failed';
  stepKind: 'resolve-project-config';
  stepErrorType: string;
  message: string;
};

export type ResolvedTaskEnv = {
  taskEnvVars: Record<string, string>;
  tmuxEnabled: boolean;
  shellSetup?: string;
};

export async function buildTaskProviders(
  opts: TaskProviderOpts,
  createConversationProvider: (options: TaskProviderOpts) => ConversationProvider
): Promise<Result<{ conversations: ConversationProvider }, RuntimeResolveError>> {
  return ok({
    conversations: createConversationProvider(opts),
  });
}

export async function resolveTaskEnv(
  task: Pick<Task, 'id' | 'name'>,
  workspace: Pick<Workspace, 'id' | 'path' | 'workspaceRegistry'>,
  projectPath: string,
  settings: ProjectSettingsProvider,
  repoFacts: RepoFactsSource
): Promise<Result<ResolvedTaskEnv, ResolveTaskEnvError>> {
  // Effective default branch through the blessed resolver (spec:
  // github-git-settings §2); null (unresolvable) omits the env var.
  const [effective, tmux, projectConfig] = await Promise.all([
    resolveProjectEffectiveSettings({ settings, repoFacts }),
    settings.resolveTmux(),
    workspace.workspaceRegistry.getProjectConfig({ workspaceId: workspace.id }),
  ]);
  const defaultBranch = effective.defaultBranch.value?.branch ?? null;
  if (!projectConfig.success) {
    return err({
      type: 'setup-failed',
      stepKind: 'resolve-project-config',
      stepErrorType: projectConfig.error.type,
      message: `Could not resolve project config for workspace ${workspace.id} (${projectConfig.error.type})`,
    });
  }
  return ok({
    taskEnvVars: getTaskEnvVars({
      taskId: task.id,
      taskName: task.name,
      taskPath: workspace.path,
      projectPath,
      defaultBranch,
      portSeed: workspace.path,
    }),
    tmuxEnabled: tmux.value,
    shellSetup: projectConfig.data.resolved.shellSetup?.value,
  });
}
