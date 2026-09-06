import { Button, Resizable, toast, useCollapsiblePanelBinding } from '@emdash/ui/react/primitives';
import { Loader2 } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { useEffect, useMemo, useState } from 'react';
import { CadTaskRunLifecycle } from '@core/features/cad/contributions/browser/cad-task-run-lifecycle';
import {
  getTaskManagerStore,
  getTaskStore,
  taskHostActionAvailability,
  taskErrorMessage,
  taskViewKind,
} from '@core/features/tasks/api/browser/task-state/task-selectors';
import { useTaskViewContext } from '@core/features/tasks/contributions/browser/task-view-context';
import { taskPanelLayoutsMemento } from '@core/features/tasks/contributions/mementos';
import { useTaskComposition } from '@core/features/workbench/api/browser/task-composition-context';
import { taskTabView } from '@core/features/workbench/api/browser/task-tab-registry';
import { useWorkspaceLayoutContext } from '@core/features/workbench/contributions/browser/layout-provider';
import { getWorkspacesWireClient } from '@core/features/workspaces/api/browser/client';
import { projectAvailabilityUi } from '@core/manifests/browser/project-availability-ui';
import { createLayoutStorage } from '@core/primitives/mementos/browser';
import { TaskMainColumn } from './view/task-main-column';
import { TaskSidebar } from './view/task-sidebar';

/** The task view's shared loading presentation: a centered spinner with an optional label. */
export function TaskViewLoadingState({ label }: { label?: string }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-3">
      <Loader2 className="h-5 w-5 animate-spin text-foreground-muted" />
      {label && <p className="font-sans text-xs text-foreground-muted">{label}</p>}
    </div>
  );
}

export const TaskMainPanel = observer(function TaskMainPanel() {
  const { projectId } = useTaskViewContext();

  return (
    <projectAvailabilityUi.Boundary projectId={projectId}>
      <TaskMainPanelContent />
    </projectAvailabilityUi.Boundary>
  );
});

const TaskMainPanelContent = observer(function TaskMainPanelContent() {
  const { projectId, taskId } = useTaskViewContext();
  const taskStore = getTaskStore(projectId, taskId);
  const kind = taskViewKind(taskStore, projectId);
  const hostAction = taskHostActionAvailability(projectId);
  const hostActionDisabledReason =
    hostAction.kind === 'disabled'
      ? (projectAvailabilityUi.getLiveActionDisabledReason(projectId) ??
        projectAvailabilityUi.defaultLiveActionDisabledReason)
      : undefined;
  const workspaceId =
    taskStore && 'workspaceId' in taskStore.data ? taskStore.data.workspaceId : undefined;

  if (kind === 'creating') {
    return <TaskViewLoadingState label="Creating chat…" />;
  }

  if (kind === 'create-error') {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center p-8">
        <div className="flex max-w-xs flex-col items-center gap-2 text-center">
          <p className="font-sans text-sm font-medium text-foreground-destructive">
            Error creating chat
          </p>
          <p className="font-sans text-xs text-foreground-passive">{taskErrorMessage(taskStore)}</p>
        </div>
      </div>
    );
  }

  if (kind === 'project-hydrating') {
    return <TaskViewLoadingState label="Loading project…" />;
  }

  if (kind === 'provisioning' && taskStore) {
    return <TaskProvisionLoader projectId={projectId} taskId={taskId} taskStore={taskStore} />;
  }

  if (kind === 'provision-error' && taskStore) {
    return (
      <TaskProvisionLoader projectId={projectId} taskId={taskId} taskStore={taskStore} error />
    );
  }

  if (taskStore?.state === 'unprovisioned' && taskStore.workspaceObservedStatus === 'missing') {
    return (
      <MissingWorkspaceState
        actionDisabledReason={hostActionDisabledReason}
        reprovision={() => reprovisionWorkspace(projectId, taskId, workspaceId!, false)}
        removeAndReprovision={() => reprovisionWorkspace(projectId, taskId, workspaceId!, true)}
      />
    );
  }

  if (kind === 'project-error') {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center p-8">
        <div className="flex max-w-xs flex-col items-center gap-2 text-center">
          <p className="font-sans text-sm font-medium text-foreground-destructive">
            Failed to set up chat workspace
          </p>
          <p className="font-sans text-xs text-foreground-muted">{taskErrorMessage(taskStore)}</p>
        </div>
      </div>
    );
  }

  if (kind === 'idle' && hostActionDisabledReason) {
    return (
      <MissingWorkspaceState
        title="Workspace is unavailable"
        description="The chat is still available, but its project files cannot be reached right now."
        actionDisabledReason={hostActionDisabledReason}
        reprovision={() =>
          getTaskManagerStore(projectId)?.provisionTask(taskId) ?? Promise.resolve()
        }
      />
    );
  }

  if (kind === 'idle' || kind === 'teardown') {
    return <TaskViewLoadingState label="Preparing chat workspace…" />;
  }

  if (kind === 'teardown-error') {
    return (
      <div className="flex h-full w-full flex-col items-center justify-center p-8">
        <div className="flex max-w-xs flex-col items-center gap-2 text-center">
          <p className="font-sans text-sm font-medium text-foreground-destructive">
            Failed to tear down workspace
          </p>
          <p className="font-sans text-xs text-foreground-muted">{taskErrorMessage(taskStore)}</p>
        </div>
      </div>
    );
  }

  if (kind === 'missing') {
    return <MissingWorkspaceState />;
  }

  return <ReadyTaskMainPanel />;
});

function MissingWorkspaceState({
  title = 'Chat workspace is missing',
  description = 'Hardcore could not activate this chat workspace. Recreate it or remove the chat.',
  actionDisabledReason,
  reprovision,
  removeAndReprovision,
}: {
  title?: string;
  description?: string;
  actionDisabledReason?: string;
  reprovision?: () => Promise<void>;
  removeAndReprovision?: () => Promise<void>;
}) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2 p-8 text-center">
      <p className="text-sm font-medium text-foreground">{title}</p>
      <p className="max-w-sm text-xs text-foreground-muted">{description}</p>
      {reprovision && (
        <div className="mt-2 flex gap-2">
          <Button
            size="sm"
            variant="secondary"
            disabled={!!actionDisabledReason}
            title={actionDisabledReason}
            aria-label={
              actionDisabledReason ? `Re-provision. ${actionDisabledReason}` : 'Re-provision'
            }
            onClick={() => void reprovision()}
          >
            Re-provision
          </Button>
          {removeAndReprovision && (
            <Button
              size="sm"
              variant="ghost"
              disabled={!!actionDisabledReason}
              title={actionDisabledReason}
              aria-label={
                actionDisabledReason
                  ? `Remove and re-provision. ${actionDisabledReason}`
                  : 'Remove and re-provision'
              }
              onClick={() => void removeAndReprovision()}
            >
              Remove and re-provision
            </Button>
          )}
        </div>
      )}
    </div>
  );
}

async function reprovisionWorkspace(
  projectId: string,
  taskId: string,
  workspaceId: string,
  removeFirst: boolean
): Promise<void> {
  if (
    removeFirst &&
    !window.confirm(
      'Remove this workspace and permanently discard any uncommitted files or changes, then ' +
        're-provision it? This cannot be undone.'
    )
  ) {
    return;
  }
  try {
    const client = await getWorkspacesWireClient();
    const result = removeFirst
      ? await client.removeAndReprovision({ workspaceId })
      : await client.reprovision({ workspaceId });
    if (!result.success) throw new Error(result.error.message);
    await getTaskManagerStore(projectId)?.provisionTask(taskId);
  } catch (error) {
    toast.error('Could not re-provision workspace', {
      description: error instanceof Error ? error.message : String(error),
    });
  }
}

const PROVISION_LOADER_DELAY_MS = 300;

/** Human labels for the host createWorktree stages streamed via the records overlay. */
const CREATION_STAGE_LABELS: Record<string, string> = {
  inspect: 'Inspecting project files',
  'resolve-base': 'Preparing the project baseline',
  'fetch-base': 'Syncing project files',
  'add-worktree': 'Creating the chat workspace',
  verify: 'Verifying project files',
};

const TaskProvisionLoader = observer(function TaskProvisionLoader({
  projectId,
  taskId,
  taskStore,
  error = false,
}: {
  projectId: string;
  taskId: string;
  taskStore: NonNullable<ReturnType<typeof getTaskStore>>;
  error?: boolean;
}) {
  const showLoader = useDelayedVisible(error ? 0 : PROVISION_LOADER_DELAY_MS);
  const errorMessage = taskErrorMessage(taskStore);
  const creation = taskStore.workspaceCreation;
  const failedCreation =
    taskStore.workspaceCreateOutcome?.status === 'failed' ? taskStore.workspaceCreateOutcome : null;

  const retry = () => {
    void getTaskManagerStore(projectId)?.provisionTask(taskId);
  };
  const action = taskHostActionAvailability(projectId);
  const retryDisabledReason =
    action.kind === 'disabled'
      ? (projectAvailabilityUi.getLiveActionDisabledReason(projectId) ??
        projectAvailabilityUi.defaultLiveActionDisabledReason)
      : undefined;

  if (!showLoader) {
    return null;
  }

  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-3 p-8">
      {!error && <Loader2 className="size-5 animate-spin text-foreground-muted" />}
      <p className="text-sm font-medium text-foreground">
        {error
          ? failedCreation
            ? 'Workspace creation failed'
            : 'Workspace activation failed'
          : creation
            ? 'Creating workspace…'
            : 'Activating workspace…'}
      </p>
      {!error && creation && (
        <p className="text-center font-sans text-xs text-foreground-muted">
          {CREATION_STAGE_LABELS[creation.stage] ?? creation.stage}…
        </p>
      )}
      {error && (
        <p className="text-center font-sans text-xs text-foreground-muted">
          {failedCreation
            ? [
                failedCreation.stage ? `Failed at ${failedCreation.stage}` : null,
                failedCreation.message ?? null,
              ]
                .filter(Boolean)
                .join(': ')
            : errorMessage}
        </p>
      )}
      {error && (
        <Button
          size="sm"
          variant="ghost"
          disabled={!!retryDisabledReason}
          title={retryDisabledReason}
          aria-label={retryDisabledReason ? `Retry. ${retryDisabledReason}` : 'Retry'}
          onClick={retry}
        >
          Retry
        </Button>
      )}
    </div>
  );
});

function useDelayedVisible(delayMs: number): boolean {
  const [visible, setVisible] = useState(delayMs === 0);

  useEffect(() => {
    if (delayMs === 0) {
      setVisible(true);
      return;
    }

    setVisible(false);
    const timer = window.setTimeout(() => setVisible(true), delayMs);
    return () => window.clearTimeout(timer);
  }, [delayMs]);

  return visible;
}

// Drag-to-close threshold for the right sidebar, in percent of the group.
// 280px — the old resize floor — is at least 8% of the group on any window up
// to ~3500px wide, so every width the previous UI let a user settle at stays
// a plain resize/restore, never a surprise close. Below 8% (~115px at 1440px)
// the sidebar content is unusable, so a drag settling there reads as intent
// to close rather than a resize.
const SIDEBAR_CLOSE_THRESHOLD = 8;

// Resize floor (the released builds' value): dragging shrinks the sidebar only
// down to this width; dragging past it snaps the collapsible panel's layout to
// `collapsedSize` (0), which the binding's close-threshold check turns into a
// semantic close.
const SIDEBAR_MIN_SIZE = '280px';

const ReadyTaskMainPanel = observer(function ReadyTaskMainPanel() {
  const taskView = useTaskComposition();
  // Zen is workspace-chrome data; the task sidebar hides while zen is active
  // as a derived condition — no task-chrome mutation, no task-side restore.
  const { isZenActive } = useWorkspaceLayoutContext();
  const isSidebarOpen = !taskView.isSidebarCollapsed && !isZenActive;

  // One storage facade per composition. ReadyTaskMainPanel renders below the
  // task view's space.isHydrated gate, so synchronous reads are safe by
  // contract.
  const layoutStorage = useMemo(
    () => createLayoutStorage(taskView.space, taskPanelLayoutsMemento),
    [taskView.space]
  );
  const sidebarBinding = useCollapsiblePanelBinding({
    storageKey: 'task-sidebar-layout',
    storage: layoutStorage,
    panelIds: ['task-main-area', 'task-sidebar'],
    collapsiblePanelId: 'task-sidebar',
    open: isSidebarOpen,
    onCloseRequest: () => taskView.chrome.commands.collapseSidebar(),
    closeThreshold: SIDEBAR_CLOSE_THRESHOLD,
  });

  return (
    <taskTabView.TabLayoutProvider layout={taskView.paneLayout}>
      <CadTaskRunLifecycle />
      <Resizable.Group
        orientation="horizontal"
        id="task-sidebar-layout"
        {...sidebarBinding.groupProps}
      >
        <Resizable.Panel id="task-main-area">
          <TaskMainColumn />
        </Resizable.Panel>
        {/* Collapsed = panel AND handle unmounted (sync contract: never
            program the panels). */}
        {isSidebarOpen && (
          <>
            <Resizable.Handle />
            <Resizable.Panel
              {...sidebarBinding.collapsiblePanelProps}
              defaultSize={sidebarBinding.collapsiblePanelProps.defaultSize ?? '25%'}
              minSize={SIDEBAR_MIN_SIZE}
              maxSize="50%"
              collapsible
              collapsedSize="0%"
            >
              <TaskSidebar />
            </Resizable.Panel>
          </>
        )}
      </Resizable.Group>
    </taskTabView.TabLayoutProvider>
  );
});
