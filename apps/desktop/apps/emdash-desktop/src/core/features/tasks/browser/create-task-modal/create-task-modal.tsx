import { Dialog, Select, Tooltip } from '@emdash/ui/react/primitives';
import { FolderGit2, GitBranch, Laptop, Server } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { useMemo } from 'react';
import { getMachinesStore } from '@core/features/machines/contributions/app-stores';
import { firstAvailableProjectId } from '@core/features/projects/api/browser/stores/project-selectors';
import {
  getProjectStore,
  projectData,
} from '@core/features/projects/api/browser/stores/project-selectors';
import { useProjectGitContext } from '@core/features/tasks/api/browser/create-task-modal/use-project-git-context';
import { useTaskSettings } from '@core/features/tasks/api/browser/hooks/useTaskSettings';
import { taskHostActionAvailability } from '@core/features/tasks/api/browser/task-state/task-selectors';
import { ExistingWorkspacePicker } from '@core/features/tasks/browser/task-config/existing-workspace-picker';
import { useInitialConversationState } from '@core/features/tasks/contributions/browser/task-config/initial-conversation-section';
import { useModalController } from '@core/manifests/browser/modal-api';
import { projectAvailabilityUi } from '@core/manifests/browser/project-availability-ui';
import { ConfirmButton } from '@core/primitives/keybindings/browser/confirm-button';
import { defineModal } from '@core/primitives/modals/react';
import { useNavigate } from '@core/primitives/navigation/browser/navigation-hooks';
import { getNavigation } from '@core/primitives/navigation/browser/navigation-selectors';
import type { PullRequest } from '@core/services/pull-requests/api';
import { useCreateTaskCallback } from './use-create-task-callback';
import { type LinkedType, useCreateTaskState } from './use-create-task-state';

function useDefaultProjectId(propProjectId?: string): string | undefined {
  return useMemo(() => {
    if (propProjectId) return propProjectId;
    const nav = getNavigation();
    const params = nav.currentRef.params as { projectId?: string };
    const navProjectId =
      nav.currentViewId === 'task' || nav.currentViewId === 'project'
        ? params.projectId
        : undefined;
    return navProjectId ?? firstAvailableProjectId();
    // oxlint-disable-next-line react/exhaustive-deps
  }, []); // computed once on mount
}

export const CreateTaskModal = observer(function CreateTaskModal({
  projectId,
  strategy: initialStrategy = 'from-branch',
  initialPR,
  initialWorkspaceId,
}: {
  projectId?: string;
  strategy?: 'from-branch' | 'from-issue' | 'from-pull-request';
  initialPR?: PullRequest;
  initialWorkspaceId?: string;
}) {
  const { complete } = useModalController('taskModal');
  const selectedProjectId = useDefaultProjectId(projectId);

  const { defaultBranch, isUnborn, hasRepository, currentBranch, repositoryWorkspaceId } =
    useProjectGitContext(selectedProjectId);

  const defaultLinkedType = useMemo((): LinkedType => {
    if (initialStrategy === 'from-pull-request') return 'pr';
    if (initialStrategy === 'from-issue') return 'issue';
    return null;
    // oxlint-disable-next-line react/exhaustive-deps
  }, []); // computed once on mount

  const resolvedInitialPR = initialStrategy === 'from-pull-request' ? initialPR : undefined;
  const state = useCreateTaskState(
    selectedProjectId,
    defaultBranch,
    isUnborn,
    hasRepository,
    currentBranch,
    repositoryWorkspaceId,
    resolvedInitialPR,
    defaultLinkedType,
    initialWorkspaceId
  );

  const { autoApproveByDefault } = useTaskSettings();
  const initialConversation = useInitialConversationState(
    selectedProjectId,
    undefined,
    autoApproveByDefault
  );
  const { navigate } = useNavigate();

  const { handleCreateTask, canCreate } = useCreateTaskCallback({
    selectedProjectId,
    state,
    initialConversation,
    navigate,
    onCreated: complete,
    createInitialConversation: false,
  });
  const createAvailability = selectedProjectId
    ? taskHostActionAvailability(selectedProjectId)
    : ({ kind: 'disabled' } as const);
  const createDisabledReason = !selectedProjectId
    ? 'Select a Project.'
    : createAvailability.kind === 'disabled'
      ? (projectAvailabilityUi.getLiveActionDisabledReason(selectedProjectId) ??
        projectAvailabilityUi.defaultLiveActionDisabledReason)
      : undefined;
  const project = selectedProjectId ? projectData(getProjectStore(selectedProjectId)) : null;
  const machine =
    project?.type === 'ssh'
      ? getMachinesStore().connections.find((candidate) => candidate.id === project.connectionId)
      : null;
  const locationLabel = project?.type === 'ssh' ? (machine?.name ?? 'Remote machine') : 'This Mac';
  const canCreateWorktree = hasRepository && !isUnborn;
  const availableExistingWorkspaces = state.workspaceConfig.workspaceOptions.filter(
    (workspace) => workspace.workspaceId && !workspace.disabledReason
  );
  const workspacePickerValue =
    state.workspaceConfig.presetId === 'repo-root' ||
    state.workspaceConfig.presetId === 'use-existing'
      ? state.workspaceConfig.presetId
      : 'new-worktree';

  const selectWorkspace = (value: string | null) => {
    if (!value) return;
    if (value === 'new-worktree' || value === 'repo-root') {
      state.workspaceConfig.setPresetId(value);
      return;
    }
    if (value !== 'use-existing') return;
    state.workspaceConfig.setPresetId('use-existing');
    if (!state.workspaceConfig.selectedWorkspaceId) {
      state.workspaceConfig.setSelectedWorkspaceId(
        availableExistingWorkspaces.find((workspace) => workspace.kind === 'worktree')
          ?.workspaceId ?? null
      );
    }
  };

  return (
    <>
      <Dialog.Header className="flex items-center gap-2">
        <Dialog.Title>New chat</Dialog.Title>
      </Dialog.Header>
      <Dialog.Body>
        <div className="flex w-full flex-col gap-3">
          <p className="max-w-md text-sm leading-relaxed text-foreground-muted">
            Chats can work with any CAD model, drawing, assembly, analysis, or supporting file in
            this project. Choose whether this chat shares the project folder or uses a worktree.
          </p>
          <div className="flex items-center gap-2">
            <Select.Root value={workspacePickerValue} onValueChange={selectWorkspace}>
              <Select.Trigger size="sm" aria-label="Chat workspace" className="min-w-40">
                <span className="flex min-w-0 items-center gap-1.5">
                  {workspacePickerValue === 'new-worktree' ||
                  workspacePickerValue === 'use-existing' ? (
                    <GitBranch className="size-3.5 shrink-0" />
                  ) : (
                    <FolderGit2 className="size-3.5 shrink-0" />
                  )}
                  <span className="truncate">
                    {workspacePickerValue === 'new-worktree'
                      ? 'New worktree'
                      : workspacePickerValue === 'use-existing'
                        ? 'Existing worktree'
                        : 'Project folder'}
                  </span>
                </span>
              </Select.Trigger>
              <Select.Content align="start" width="content-at-least-trigger">
                <Select.Item value="new-worktree" disabled={!canCreateWorktree}>
                  <span className="flex items-center gap-2">
                    <GitBranch className="size-3.5" />
                    New worktree
                  </span>
                </Select.Item>
                <Select.Item value="repo-root" disabled={!repositoryWorkspaceId}>
                  <span className="flex items-center gap-2">
                    <FolderGit2 className="size-3.5" />
                    Project folder
                  </span>
                </Select.Item>
                {availableExistingWorkspaces.some((workspace) => workspace.kind === 'worktree') ? (
                  <Select.Item value="use-existing">
                    <span className="flex items-center gap-2">
                      <GitBranch className="size-3.5" />
                      Existing worktree
                    </span>
                  </Select.Item>
                ) : null}
              </Select.Content>
            </Select.Root>
            <Tooltip.Root>
              <Tooltip.Trigger
                render={
                  <span
                    className="flex min-w-0 items-center gap-1.5 px-1 text-xs text-foreground-muted"
                    tabIndex={0}
                    aria-label={`Runs on ${locationLabel}`}
                  >
                    {project?.type === 'ssh' ? (
                      <Server className="size-3.5 shrink-0" />
                    ) : (
                      <Laptop className="size-3.5 shrink-0" />
                    )}
                    <span className="truncate">{locationLabel}</span>
                  </span>
                }
              />
              <Tooltip.Content>This chat runs on {locationLabel}.</Tooltip.Content>
            </Tooltip.Root>
          </div>
          {state.workspaceConfig.presetId === 'use-existing' ? (
            <ExistingWorkspacePicker
              workspaces={availableExistingWorkspaces.filter(
                (workspace) => workspace.kind === 'worktree'
              )}
              isLoading={state.workspaceConfig.workspaceOptionsLoading}
              selectedWorkspaceId={state.workspaceConfig.selectedWorkspaceId}
              onSelect={state.workspaceConfig.setSelectedWorkspaceId}
            />
          ) : null}
          <p className="text-tiny leading-4 text-foreground-muted">
            {state.workspaceConfig.presetId === 'new-worktree'
              ? `Isolated from other chats and based on ${defaultBranch?.branch ?? currentBranch ?? 'the project branch'}.`
              : 'Uses files already in this workspace. Chat history stays separate while files are shared.'}
          </p>
        </div>
      </Dialog.Body>
      <Dialog.Footer>
        <ConfirmButton
          variant="primary"
          size="sm"
          onClick={handleCreateTask}
          disabled={
            !canCreate || initialConversation.issueContextEditorOpen || !!createDisabledReason
          }
          title={createDisabledReason}
          aria-label={createDisabledReason ? `Create. ${createDisabledReason}` : 'Create'}
        >
          Create chat
        </ConfirmButton>
      </Dialog.Footer>
    </>
  );
});

export const taskModal = defineModal<void>()({
  id: 'taskModal',
  component: CreateTaskModal,
  ignoreOutsidePressAfterWindowBlur: true,
});
