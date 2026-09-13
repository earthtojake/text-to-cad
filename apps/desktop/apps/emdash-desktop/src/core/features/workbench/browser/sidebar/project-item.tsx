import { ContextMenu, DropdownMenu, Tooltip } from '@emdash/ui/react/primitives';
import {
  ChevronRight,
  FolderClosed,
  FolderInput,
  FolderOpen,
  Loader2,
  MessageSquareMore,
  MoreHorizontal,
  Plus,
  Trash2,
  TriangleAlert,
} from 'lucide-react';
import { observer } from 'mobx-react-lite';
import React, { useCallback, useEffect } from 'react';
import { ConnectionStatusDot } from '@core/features/machines/contributions/browser/connection-status-dot';
import {
  isUnregisteredProject,
  type ProjectCreationStage,
} from '@core/features/projects/api/browser/stores/project';
import {
  getProjectHostAccess,
  getProjectStore,
  projectViewKind,
} from '@core/features/projects/api/browser/stores/project-selectors';
import { useConfirmDeleteProject } from '@core/features/projects/contributions/browser/use-confirm-delete-project';
import { projectViewDef } from '@core/features/projects/contributions/views';
import { getGitRepositoryStore } from '@core/features/source-control/api/browser/stores/source-control-selectors';
import { taskHostActionAvailability } from '@core/features/tasks/api/browser/task-state/task-selectors';
import { taskViewDef } from '@core/features/tasks/contributions/views';
import { getSidebarStore } from '@core/features/workbench/contributions/browser/app-stores';
import { newChatDraftView } from '@core/features/workbench/contributions/views';
import { projectAvailabilityUi } from '@core/manifests/browser/project-availability-ui';
import { BoundShortcut } from '@core/primitives/keybindings/browser/shortcut';
import {
  useNavigate,
  useViewParams,
  useWorkspaceSlots,
} from '@core/primitives/navigation/browser/navigation-hooks';
import { cn } from '@core/primitives/styling/browser/cn';
import {
  SidebarItemMiniButton,
  SidebarMenuAction,
  SidebarMenuButton,
  SidebarMenuRow,
} from './sidebar-primitives';

const UNREGISTERED_STAGE_LABEL: Record<ProjectCreationStage, string> = {
  'creating-repo': 'Creating repository…',
  cloning: 'Cloning…',
  registering: 'Registering…',
};

export const SidebarProjectItem = observer(function SidebarProjectItem({
  projectId,
}: {
  projectId: string;
}) {
  const { navigate } = useNavigate();
  const { currentView } = useWorkspaceSlots();
  const projectParams = useViewParams(projectViewDef);
  const taskParams = useViewParams(taskViewDef);
  const confirmDeleteProject = useConfirmDeleteProject();

  const project = getProjectStore(projectId);

  const prefetchRepository = useCallback(() => {
    const repo = getGitRepositoryStore(projectId);
    void repo?.localData.load();
    void repo?.remoteData.load();
  }, [projectId]);

  const currentProjectId =
    currentView === 'task'
      ? taskParams?.projectId
      : currentView === 'project'
        ? projectParams?.projectId
        : null;
  const currentTaskId = currentView === 'task' ? taskParams?.taskId : null;

  const isProjectActive = currentProjectId === projectId && !currentTaskId;

  useEffect(() => {
    if (isProjectActive) prefetchRepository();
  }, [isProjectActive, prefetchRepository]);

  const isExpanded = getSidebarStore().expandedProjectIds.has(projectId);

  if (!project) return null;

  const sshConnectionId = project.data?.type === 'ssh' ? project.data.connectionId : null;
  const isSshProject = sshConnectionId !== null;
  const hostAccess = getProjectHostAccess(projectId);
  const hostAccessState = hostAccess?.state;
  const displayedSshConnectionState =
    !hostAccessState || hostAccessState.kind !== 'ready'
      ? hostAccessState &&
        ['connecting', 'provisioning', 'handshaking', 'attaching', 'recovering'].includes(
          hostAccessState.situation
        )
        ? 'connecting'
        : 'disconnected'
      : 'connected';
  const ProjectIcon = isSshProject ? FolderInput : isExpanded ? FolderOpen : FolderClosed;
  const projectLabel = project.name ?? 'project';
  const createAvailability = taskHostActionAvailability(projectId);
  const createDisabledReason =
    createAvailability.kind === 'disabled'
      ? (projectAvailabilityUi.getLiveActionDisabledReason(projectId) ??
        projectAvailabilityUi.defaultLiveActionDisabledReason)
      : undefined;
  const toggleProject = () => getSidebarStore().toggleProjectExpanded(projectId);
  const openChatManagement = () => navigate(projectViewDef({ projectId }));
  const removeProject = () =>
    void confirmDeleteProject({
      projectId,
      projectLabel: project.name ?? 'this project',
    });

  const renderSpinnerWithTooltip = () => {
    if (!isUnregisteredProject(project)) return null;
    const label =
      project.creation.kind === 'failed'
        ? 'Failed'
        : UNREGISTERED_STAGE_LABEL[project.creation.stage];
    return (
      <Tooltip.Root>
        <Tooltip.Trigger
          render={
            <SidebarItemMiniButton type="button" disabled aria-label="Loading">
              <Loader2 className="h-4 w-4 animate-spin text-foreground/60" />
            </SidebarItemMiniButton>
          }
        />
        <Tooltip.Content>{label}</Tooltip.Content>
      </Tooltip.Root>
    );
  };

  return (
    <>
      <ContextMenu.Root>
        <ContextMenu.Trigger>
          <SidebarMenuRow
            className="group/row flex h-8 justify-between px-1 font-medium text-foreground"
            data-active={isProjectActive || undefined}
            isActive={isProjectActive}
            onMouseDown={(e) => e.preventDefault()}
            onClick={toggleProject}
          >
            <div className="flex min-w-0 flex-1 items-center gap-1">
              {project.state === 'unregistered' ? (
                renderSpinnerWithTooltip()
              ) : (
                <SidebarItemMiniButton
                  type="button"
                  aria-label={`${isExpanded ? 'Collapse' : 'Expand'} ${projectLabel}`}
                  className="relative"
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleProject();
                  }}
                >
                  <ProjectIcon className="absolute h-4 w-4 opacity-100 transition-opacity duration-150 group-hover/row:opacity-0" />
                  <ChevronRight
                    className={cn(
                      'absolute h-4 w-4 transition-all duration-150 opacity-0 group-hover/row:opacity-100',
                      isExpanded && 'rotate-90'
                    )}
                  />
                </SidebarItemMiniButton>
              )}
              <SidebarMenuAction
                aria-label={`${isExpanded ? 'Collapse' : 'Expand'} chats in ${projectLabel}`}
                className={cn(
                  'truncate transition-colors select-none',
                  projectViewKind(getProjectStore(projectId)) === 'hydrating' &&
                    'text-foreground-tertiary-passive'
                )}
              >
                {isSshProject ? (
                  <span className="flex min-w-0 items-center gap-2">
                    <span className="truncate">{project.name}</span>
                    <ConnectionStatusDot state={displayedSshConnectionState} />
                  </span>
                ) : (
                  <span className="flex min-w-0 items-center gap-1.5">
                    <span className="truncate">{project.name}</span>
                    {projectViewKind(project) === 'context_error' && (
                      <Tooltip.Root>
                        <Tooltip.Trigger>
                          <TriangleAlert className="h-3.5 w-3.5 shrink-0 text-foreground-destructive" />
                        </Tooltip.Trigger>
                        <Tooltip.Content>Project context unavailable</Tooltip.Content>
                      </Tooltip.Root>
                    )}
                  </span>
                )}
              </SidebarMenuAction>
            </div>
            <div className="flex h-6 shrink-0 items-center">
              <DropdownMenu.Root>
                <DropdownMenu.Trigger
                  render={
                    <SidebarItemMiniButton
                      type="button"
                      aria-label={`More actions for ${projectLabel}`}
                      title="Project actions"
                      className="opacity-0 transition-opacity duration-150 group-hover/row:opacity-100 focus-visible:opacity-100 data-[popup-open]:opacity-100"
                      onClick={(event) => event.stopPropagation()}
                    >
                      <MoreHorizontal className="h-4 w-4" />
                    </SidebarItemMiniButton>
                  }
                />
                <DropdownMenu.Content align="end" onClick={(event) => event.stopPropagation()}>
                  <DropdownMenu.Item onClick={openChatManagement}>
                    <MessageSquareMore className="size-4" />
                    View all chats
                  </DropdownMenu.Item>
                  <DropdownMenu.Separator />
                  <DropdownMenu.Item variant="destructive" onClick={removeProject}>
                    <Trash2 className="size-4" />
                    Remove Project
                  </DropdownMenu.Item>
                </DropdownMenu.Content>
              </DropdownMenu.Root>
              <Tooltip.Root>
                <Tooltip.Trigger
                  className="h-6"
                  render={
                    <SidebarItemMiniButton
                      type="button"
                      aria-label={
                        createDisabledReason
                          ? `New chat in ${projectLabel}. ${createDisabledReason}`
                          : `New chat in ${projectLabel}`
                      }
                      className="opacity-0 transition-opacity duration-150 group-hover/row:opacity-100 focus-visible:opacity-100"
                      onPointerEnter={() => prefetchRepository()}
                      onClick={(e) => {
                        e.stopPropagation();
                        navigate(newChatDraftView(projectId));
                      }}
                      disabled={project.state === 'unregistered' || !!createDisabledReason}
                    >
                      <Plus className="h-4 w-4" />
                    </SidebarItemMiniButton>
                  }
                />
                <Tooltip.Content>
                  {createDisabledReason ?? (
                    <>
                      New chat
                      <BoundShortcut command="app.newTask" variant="keycaps" />
                    </>
                  )}
                </Tooltip.Content>
              </Tooltip.Root>
            </div>
          </SidebarMenuRow>
        </ContextMenu.Trigger>
        <ContextMenu.Content>
          <ContextMenu.Item onClick={openChatManagement}>
            <MessageSquareMore className="size-4" />
            View all chats
          </ContextMenu.Item>
          <ContextMenu.Separator />
          <ContextMenu.Item variant="destructive" onClick={removeProject}>
            <Trash2 className="size-4" />
            Remove Project
          </ContextMenu.Item>
        </ContextMenu.Content>
      </ContextMenu.Root>
    </>
  );
});

interface BaseProjectItemProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  isActive: boolean;
}

export function BaseProjectItem({ isActive, className, ...props }: BaseProjectItemProps) {
  return (
    <SidebarMenuButton
      className={cn('justify-between flex item px-1 py-1', className)}
      isActive={isActive}
      {...props}
    />
  );
}
