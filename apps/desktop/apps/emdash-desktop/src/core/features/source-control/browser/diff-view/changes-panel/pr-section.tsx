import { EmptyState } from '@emdash/ui/react/components';
import { Button, SplitButton, Tooltip, useToast } from '@emdash/ui/react/primitives';
import { Plus, RefreshCw } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import {
  asAvailableProject,
  getProjectStore,
} from '@core/features/projects/api/browser/stores/project-selectors';
import { getGitRepositoryStore } from '@core/features/source-control/api/browser/stores/source-control-selectors';
import { getTaskGitCheckoutStore } from '@core/features/source-control/api/browser/stores/task-source-control-selectors';
import { gitCheckoutStoreToken } from '@core/features/source-control/contributions/browser/workspace-store-tokens';
import { useTaskViewContext } from '@core/features/tasks/contributions/browser/task-view-context';
import {
  useTaskComposition,
  useWorkspace,
  useWorkspaceId,
} from '@core/features/workbench/api/browser/task-composition-context';
import { useOpenModal } from '@core/manifests/browser/modal-api';
import { projectAvailabilityUi } from '@core/manifests/browser/project-availability-ui';
import { cn } from '@core/primitives/styling/browser/cn';
import { pullRequestErrorMessage } from '@core/services/pull-requests/api';
import { getPullRequestsRuntimeClient } from '@core/services/pull-requests/api/client';
import { ChangesViewModeToggle } from './components/changes-view-mode-toggle';
import { CommitRangeCommitsList } from './components/pr-entry/commits-list';
import { PullRequestEntry } from './components/pr-entry/pr-entry';
import { type CommitRange, useCommits } from './components/pr-entry/use-commits';
import { SectionHeader } from './components/section-header';
import { useChangesViewMode } from './hooks/use-changes-view-mode';

const BRANCH_COMMITS_EMPTY_STATE = {
  label: 'No commits',
  description: 'No commits ahead of the base branch.',
};

/**
 * Facts shared by the section header (label, count, actions) and the body.
 * Header and body are separate components in the sections group, so each calls
 * this hook; the underlying react-query cache dedupes the commit lookups.
 */
function usePullRequestsSectionModel() {
  const { projectId, taskId } = useTaskViewContext();
  const workspaceId = useWorkspaceId();
  const workspace = useWorkspace();
  const taskView = useTaskComposition();
  const prStore = taskView.prStore;
  const repository = getGitRepositoryStore(projectId);
  const repositoryUrl = repository?.pullRequestRepositoryUrl ?? null;
  const providerRepositoryObservation = repository?.providerRepositoryObservation ?? {
    kind: 'unavailable' as const,
  };
  const taskBranch = getTaskGitCheckoutStore(projectId, taskId)?.branchName;
  const pullRequests = prStore?.pullRequests ?? [];
  const pullRequestsObservation = prStore?.pullRequestsObservation ?? {
    kind: 'unavailable' as const,
  };
  const currentPr = prStore?.currentPr;
  const defaultBranch = repository?.defaultBranch;
  const gitCheckout = workspace.get(gitCheckoutStoreToken);
  const headOid = gitCheckout.headOid;
  const branchCommitRange: CommitRange | undefined =
    !currentPr && defaultBranch?.oid && headOid && defaultBranch.oid !== headOid
      ? {
          source: 'branch',
          baseRefOid: defaultBranch.oid,
          headRefOid: headOid,
          revision: gitCheckout.statusRevision,
        }
      : undefined;
  const branchCommits = useCommits(projectId, workspaceId, branchCommitRange);
  const branchCommitCount = branchCommits.data?.pages[0]?.aheadCount;

  const showBranchCommits =
    !!branchCommitRange && branchCommitCount !== undefined && branchCommitCount > 0;

  return {
    projectId,
    taskId,
    workspaceId,
    repositoryUrl,
    providerRepositoryObservation,
    taskBranch,
    pullRequests,
    pullRequestsObservation,
    currentPr,
    branchCommitRange,
    showBranchCommits,
    sectionLabel: showBranchCommits ? 'Branch Commits' : 'Pull Requests',
    sectionCount: showBranchCommits ? (branchCommitCount ?? 0) : pullRequests.length,
  };
}

/** Always-visible header row; rendered as a direct child of the sections group. */
export const PullRequestsSectionHeader = observer(function PullRequestsSectionHeader({
  onSyncError,
}: {
  onSyncError: (message: string | null) => void;
}) {
  const taskView = useTaskComposition();
  const changesView = taskView.diffView?.changesView;
  const {
    projectId,
    taskId,
    workspaceId,
    repositoryUrl,
    taskBranch,
    pullRequests,
    currentPr,
    sectionLabel,
    sectionCount,
  } = usePullRequestsSectionModel();
  const openCreatePrModal = useOpenModal('createPrModal');
  const { toast } = useToast();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const { mode: viewMode, setMode: setViewMode } = useChangesViewMode('pr');
  const context = asAvailableProject(getProjectStore(projectId));
  const hostActionReason = context
    ? projectAvailabilityUi.getLiveActionDisabledReason(projectId)
    : 'Unavailable until access to this Project is restored.';
  const hostActionDisabled = hostActionReason !== null;

  const hasOpenPr = pullRequests.some((p) => p.status === 'open');

  const onCreatePr =
    taskBranch && repositoryUrl
      ? () => {
          void openCreatePrModal({
            projectId,
            taskId,
            repositoryUrl: repositoryUrl ?? '',
            branchName: taskBranch,
            draft: false,
            workspaceId,
          });
        }
      : undefined;

  const onCreateDraftPr =
    taskBranch && repositoryUrl
      ? () => {
          void openCreatePrModal({
            projectId,
            taskId,
            repositoryUrl: repositoryUrl ?? '',
            branchName: taskBranch,
            draft: true,
            workspaceId,
          });
        }
      : undefined;

  const prActions = [
    { id: 'create-pr', label: 'Create PR', action: () => onCreatePr?.() },
    { id: 'create-draft-pr', label: 'Create draft PR', action: () => onCreateDraftPr?.() },
  ];
  const [selectedPrActionId, setSelectedPrActionId] = useState<string | undefined>(undefined);

  const handleRefresh = async () => {
    if (hostActionDisabled || !repositoryUrl) return;
    setIsRefreshing(true);
    onSyncError(null);
    try {
      const client = await getPullRequestsRuntimeClient();
      const result = await client.sync({ repositoryUrl });
      if (!result.success) {
        const message = pullRequestErrorMessage(result.error);
        onSyncError(message);
        toast.error('Failed to refresh pull requests', { description: message });
      }
    } catch (error) {
      toast.error('Failed to refresh pull requests', {
        description: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setIsRefreshing(false);
    }
  };

  const createPrTooltip = !repositoryUrl
    ? 'Pull requests unavailable'
    : hostActionReason
      ? hostActionReason
      : hasOpenPr
        ? 'A pull request is already open'
        : 'Create a pull request';

  if (!changesView) return null;

  return (
    <SectionHeader
      label={sectionLabel}
      count={sectionCount}
      collapsed={!changesView.expandedSections.pullRequests}
      onToggleCollapsed={() => changesView.toggleExpanded('pullRequests')}
      actions={
        <>
          {currentPr && (
            <ChangesViewModeToggle
              value={viewMode}
              onChange={setViewMode}
              label="Pull request files"
            />
          )}
          <Tooltip.Root>
            <Tooltip.Trigger
              render={
                <SplitButton
                  variant="secondary"
                  size="xs"
                  options={prActions.map(({ id, label }) => ({ id, label }))}
                  selectedId={selectedPrActionId}
                  onSelectedChange={setSelectedPrActionId}
                  commitOnSelect={false}
                  onAction={(id) => {
                    if (!hostActionDisabled) prActions.find((a) => a.id === id)?.action();
                  }}
                  disabled={hasOpenPr || !onCreatePr || !onCreateDraftPr}
                  aria-disabled={hostActionDisabled}
                  aria-description={hostActionReason ?? undefined}
                  icon={<Plus className="size-3" />}
                />
              }
            />
            <Tooltip.Content>{createPrTooltip}</Tooltip.Content>
          </Tooltip.Root>
          <Tooltip.Root>
            <Tooltip.Trigger
              render={
                <Button
                  variant="secondary"
                  size="xs"
                  icon
                  onClick={() => void handleRefresh()}
                  disabled={isRefreshing}
                  aria-disabled={hostActionDisabled}
                  aria-description={hostActionReason ?? undefined}
                >
                  <RefreshCw className={cn('size-3', isRefreshing && 'animate-spin')} />
                </Button>
              }
            />
            <Tooltip.Content>{hostActionReason ?? 'Refresh pull requests'}</Tooltip.Content>
          </Tooltip.Root>
        </>
      }
    />
  );
});

/** Section body; mounted inside a Resizable.Panel only while the section is expanded. */
export const PullRequestsSectionBody = observer(function PullRequestsSectionBody({
  syncError,
}: {
  syncError: string | null;
}) {
  const {
    repositoryUrl,
    providerRepositoryObservation,
    pullRequests,
    pullRequestsObservation,
    currentPr,
    branchCommitRange,
    showBranchCommits,
  } = usePullRequestsSectionModel();

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      {pullRequestsObservation.kind === 'stale' ? (
        <p
          role="status"
          className="border-t border-border px-2.5 py-2 text-xs text-foreground-muted"
        >
          Showing previously observed pull requests
        </p>
      ) : null}
      {currentPr ? (
        <PullRequestEntry key={currentPr.url} pr={currentPr} />
      ) : showBranchCommits && branchCommitRange ? (
        <BranchCommitsEntry range={branchCommitRange} />
      ) : providerRepositoryObservation.kind === 'unavailable' ? (
        <EmptyState
          label="Repository details unavailable"
          description="Provider repository data has not been observed for this Project yet."
        />
      ) : !repositoryUrl ? (
        <EmptyState
          label="Pull requests unavailable"
          description="Pull requests are currently available only for configured GitHub remotes."
        />
      ) : pullRequestsObservation.kind === 'unavailable' ? (
        <EmptyState
          label="Pull requests unavailable"
          description="Pull request data has not been observed for this Project yet."
        />
      ) : pullRequests.length === 0 ? (
        <EmptyState
          label={syncError ? 'Could not load pull requests' : 'No pull requests'}
          description={syncError ?? 'Push your branch and create a PR to start a review.'}
        />
      ) : null}
    </div>
  );
});

function BranchCommitsEntry({ range }: { range: CommitRange }) {
  return (
    <div className="flex min-h-0 flex-1 flex-col border-t border-border">
      <div className="min-h-0 flex-1 px-2.5">
        <CommitRangeCommitsList range={range} emptyState={BRANCH_COMMITS_EMPTY_STATE} />
      </div>
    </div>
  );
}
