import { Button, Checkbox, Dialog } from '@emdash/ui/react/primitives';
import { useQuery } from '@tanstack/react-query';
import { TriangleAlert } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { useMemo, useState } from 'react';
import { getTasksWireClient } from '@core/features/tasks/api/browser/client';
import { useTaskSettings } from '@core/features/tasks/api/browser/hooks/useTaskSettings';
import { taskHostActionAvailability } from '@core/features/tasks/api/browser/task-state/task-selectors';
import { useModalController } from '@core/manifests/browser/modal-api';
import { projectAvailabilityUi } from '@core/manifests/browser/project-availability-ui';
import { ConfirmButton } from '@core/primitives/keybindings/browser/confirm-button';
import { defineModal } from '@core/primitives/modals/react';

export type DeleteTaskModalArgs = {
  projectId: string;
  tasks: Array<{ taskId: string; taskName: string }>;
};

export type DeleteTaskModalResult = {
  deleteWorktree: boolean;
  deleteBranch: boolean;
  deleteConversations: boolean;
};

export const DeleteTaskModal = observer(function DeleteTaskModal({
  projectId,
  tasks,
}: DeleteTaskModalArgs) {
  const { complete, dismiss } = useModalController('deleteTaskModal');
  const { deleteBranchByDefault } = useTaskSettings();
  const [deleteWorktree, setDeleteWorktree] = useState(true);
  const deleteBranchOverride: boolean | undefined = undefined;
  const [deleteConversations, setDeleteConversations] = useState(true);

  const count = tasks.length;
  const isBulk = count > 1;

  const taskIds = useMemo(() => tasks.map((t) => t.taskId), [tasks]);
  const hostAction = taskHostActionAvailability(projectId);
  const hostActionDisabledReason =
    hostAction.kind === 'disabled'
      ? (projectAvailabilityUi.getLiveActionDisabledReason(projectId) ??
        projectAvailabilityUi.defaultLiveActionDisabledReason)
      : undefined;

  const { data: preflight = null } = useQuery({
    queryKey: ['deleteTaskPreflight', projectId, taskIds],
    enabled: !hostActionDisabledReason,
    staleTime: Infinity,
    queryFn: async () => {
      try {
        return (await (await getTasksWireClient()).getDeletePreflight({ projectId, taskIds }))
          .tasks;
      } catch {
        return [];
      }
    },
  });

  const isLoading = !hostActionDisabledReason && preflight === null;

  const worktreeTasks = preflight?.filter((t) => t.hasWorktree) ?? [];
  const dirtyTasks = preflight?.filter((t) => t.hasUncommittedChanges) ?? [];
  const branchTasks = preflight?.filter((t) => t.hasDeletableBranch) ?? [];
  // Nothing is queued for an unreachable host (ADR 0006): artifact deletion is
  // disabled with the reason shown, never silently deferred.
  const hostUnreachable =
    !!hostActionDisabledReason || worktreeTasks.some((t) => t.hostReachable === false);

  const showWorktreeCheckbox = !isLoading && worktreeTasks.length > 0;
  const showBranchCheckbox = !isLoading && branchTasks.length > 0;
  const effectiveDeleteWorktree = showWorktreeCheckbox && deleteWorktree && !hostUnreachable;
  const effectiveDeleteBranch = deleteBranchOverride ?? deleteBranchByDefault;
  const shouldDeleteBranch = effectiveDeleteWorktree && effectiveDeleteBranch;

  const handleWorktreeChange = (checked: boolean) => {
    setDeleteWorktree(checked);
  };

  const title = isBulk ? `Delete ${count} models` : 'Delete model';

  const description = isBulk
    ? `${count} models and their design histories will be permanently deleted. This action cannot be undone.`
    : `"${tasks[0]!.taskName}" and its design history will be permanently deleted. This action cannot be undone.`;

  const worktreeLabel = isBulk
    ? `Delete associated model files (${worktreeTasks.length} of ${count} models)`
    : 'Delete associated model files';

  const dirtyWarning = (() => {
    if (dirtyTasks.length === 0) return null;
    if (!isBulk) {
      const stats = dirtyTasks[0]?.changedLines;
      const lines =
        stats && (stats.added > 0 || stats.deleted > 0)
          ? ` (+${stats.added} −${stats.deleted})`
          : '';
      return `"${tasks[0]!.taskName}" has unsaved file changes${lines} that will be lost.`;
    }
    const names = dirtyTasks
      .map((t) => `"${tasks.find((task) => task.taskId === t.taskId)?.taskName ?? t.taskId}"`)
      .join(', ');
    return `${dirtyTasks.length} ${dirtyTasks.length === 1 ? 'model has' : 'models have'} unsaved file changes that will be lost: ${names}`;
  })();

  const unpushedWarning = (() => {
    const unpushed = worktreeTasks.filter((t) => (t.unpushedCommits ?? 0) > 0);
    if (unpushed.length === 0) return null;
    if (!isBulk) {
      return `"${tasks[0]!.taskName}" has local history that has not been synced.`;
    }
    return `${unpushed.length} ${unpushed.length === 1 ? 'model has' : 'models have'} local history that has not been synced.`;
  })();

  return (
    <>
      <Dialog.Header showCloseButton={false}>
        <Dialog.Title>{title}</Dialog.Title>
      </Dialog.Header>
      <Dialog.Body className="flex flex-col gap-4 pt-0">
        <p className="text-sm text-foreground-muted">{description}</p>

        {showWorktreeCheckbox && (
          <div className="flex flex-col gap-3">
            {showWorktreeCheckbox && (
              <div className="flex flex-col gap-2">
                <label
                  className="flex cursor-pointer items-center gap-2 text-sm aria-disabled:cursor-not-allowed aria-disabled:opacity-50"
                  aria-disabled={hostUnreachable}
                >
                  <Checkbox
                    checked={effectiveDeleteWorktree}
                    onCheckedChange={(checked) => handleWorktreeChange(Boolean(checked))}
                    disabled={hostUnreachable}
                  />
                  {worktreeLabel}
                </label>
                {hostUnreachable && (
                  <div className="flex items-start gap-1.5 rounded-md bg-background-warning px-3 py-2 text-xs text-foreground-warning">
                    <TriangleAlert className="mt-px size-3.5 shrink-0" />
                    <span>
                      {hostActionDisabledReason ?? 'Live Project access is unavailable.'} The model
                      files cannot be deleted right now. The model record can still be removed, and
                      its files can be cleaned up after the project reconnects.
                    </span>
                  </div>
                )}
                {effectiveDeleteWorktree && dirtyWarning && (
                  <div className="flex items-start gap-1.5 rounded-md bg-background-warning px-3 py-2 text-xs text-foreground-warning">
                    <TriangleAlert className="mt-px size-3.5 shrink-0" />
                    <span>{dirtyWarning}</span>
                  </div>
                )}
                {effectiveDeleteWorktree && unpushedWarning && (
                  <div className="flex items-start gap-1.5 rounded-md bg-background-warning px-3 py-2 text-xs text-foreground-warning">
                    <TriangleAlert className="mt-px size-3.5 shrink-0" />
                    <span>{unpushedWarning}</span>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {hostActionDisabledReason && (
          <div
            role="status"
            className="flex items-start gap-1.5 rounded-md bg-background-warning px-3 py-2 text-xs text-foreground-warning"
          >
            <TriangleAlert className="mt-px size-3.5 shrink-0" />
            <span>
              {hostActionDisabledReason} The model record can still be deleted without removing its
              associated files.
            </span>
          </div>
        )}

        <label
          className="flex cursor-pointer items-center gap-2 text-sm aria-disabled:cursor-not-allowed aria-disabled:opacity-50"
          aria-disabled={!!hostActionDisabledReason}
        >
          <Checkbox
            checked={deleteConversations && !hostActionDisabledReason}
            onCheckedChange={(checked) => setDeleteConversations(Boolean(checked))}
            disabled={!!hostActionDisabledReason}
            aria-label={
              hostActionDisabledReason
                ? `Delete design history. ${hostActionDisabledReason}`
                : 'Delete design history'
            }
          />
          Delete design history
        </label>
      </Dialog.Body>
      <Dialog.Footer>
        <Button variant="secondary" onClick={dismiss}>
          Cancel
        </Button>
        <ConfirmButton
          variant="destructive"
          disabled={isLoading}
          onClick={() =>
            complete({
              deleteWorktree: effectiveDeleteWorktree,
              deleteBranch: showBranchCheckbox && shouldDeleteBranch,
              deleteConversations: deleteConversations && !hostActionDisabledReason,
            })
          }
        >
          {isLoading ? 'Loading...' : isBulk ? `Delete ${count} models` : 'Delete'}
        </ConfirmButton>
      </Dialog.Footer>
    </>
  );
});

export const deleteTaskModal = defineModal<DeleteTaskModalResult>()({
  id: 'deleteTaskModal',
  component: DeleteTaskModal,
  size: 'sm',
});
