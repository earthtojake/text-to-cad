import type { GitChange } from '@emdash/core/runtimes/git/api';
import { EmptyState } from '@emdash/ui/react/components';
import { Button, toast } from '@emdash/ui/react/primitives';
import { Minus } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { gitCheckoutStoreToken } from '@core/features/source-control/contributions/browser/workspace-store-tokens';
import { formatErrorType } from '@core/features/tasks/api/browser/utils';
import {
  useTaskComposition,
  useWorkspace,
} from '@core/features/workbench/api/browser/task-composition-context';
import { HEAD_REF } from '@core/primitives/git/api';
import { commitRef } from '@core/primitives/git/api';
import { activeDiffEntry } from '../pane-selectors';
import { ActionCard } from './components/action-card';
import { ChangesListOrTree } from './components/changes-list-or-tree';
import { ChangesViewModeToggle } from './components/changes-view-mode-toggle';
import { CommitCard } from './components/commit-card';
import { SectionHeader } from './components/section-header';
import { useChangesViewMode } from './hooks/use-changes-view-mode';
import { usePrefetchDiffModels } from './hooks/use-prefetch-diff-models';

/** Always-visible header row; rendered as a direct child of the sections group. */
export const StagedSectionHeader = observer(function StagedSectionHeader() {
  const taskView = useTaskComposition();
  const workspace = useWorkspace();
  const git = workspace.get(gitCheckoutStoreToken);
  const changesView = taskView.diffView?.changesView;
  const { mode: viewMode, setMode: setViewMode } = useChangesViewMode('staged');

  if (!changesView) return null;

  return (
    <SectionHeader
      label="Staged"
      count={git.stagedFileChanges.length}
      selectionState={changesView.stagedSelectionState}
      onToggleAll={() => changesView.toggleAllStaged()}
      actions={<ChangesViewModeToggle value={viewMode} onChange={setViewMode} label="Staged" />}
      collapsed={!changesView.expandedSections.staged}
      onToggleCollapsed={() => changesView.toggleExpanded('staged')}
    />
  );
});

/** Section body; mounted inside a Resizable.Panel only while the section is expanded. */
export const StagedSectionBody = observer(function StagedSectionBody() {
  const taskView = useTaskComposition();
  const workspace = useWorkspace();
  const git = workspace.get(gitCheckoutStoreToken);
  const diffView = taskView.diffView;
  const changesView = diffView?.changesView;

  const changes = git.stagedFileChanges;
  const hasChanges = changes.length > 0;

  const _activeDiff = activeDiffEntry(taskView.activePane);
  const activePath = _activeDiff?.diffGroup === 'staged' ? _activeDiff.path : undefined;

  const prefetch = usePrefetchDiffModels('staged', HEAD_REF);

  const { mode: viewMode } = useChangesViewMode('staged');

  if (!diffView || !changesView) return null;

  const handleSelectChange = (change: GitChange) => {
    taskView.activePane.open(
      'diff',
      {
        activeFile: {
          path: change.path,
          type: 'git',
          group: 'staged',
          originalRef: commitRef('HEAD'),
        },
        status: change.status,
      },
      { preview: true }
    );
  };

  const handleDoubleClickChange = (change: GitChange) => {
    taskView.activePane.open(
      'diff',
      {
        activeFile: {
          path: change.path,
          type: 'git',
          group: 'staged',
          originalRef: commitRef('HEAD'),
        },
        status: change.status,
      },
      { preview: false }
    );
  };

  const handleUnstageSelection = () => {
    const paths = [...changesView.stagedSelection];
    void git.unstageFiles(paths).then((result) => {
      if (!result.success) {
        toast.error(`Failed to unstage changes: ${formatErrorType(result.error)} `);
        return;
      }
      changesView.removeStagedSelection(paths);
    });
  };

  const handleUnstageAll = () => {
    void git.unstageAllFiles().then((result) => {
      if (!result.success) {
        toast.error(`Failed to unstage changes: ${formatErrorType(result.error)} `);
      }
    });
  };

  return (
    <>
      {!hasChanges && (
        <EmptyState
          label="Nothing staged"
          description="Stage files above to include them in a commit."
        />
      )}
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {hasChanges && changesView.stagedSelection.size > 0 && (
          <ActionCard
            selectedCount={changesView.stagedSelection.size}
            selectionActions={
              <Button
                variant="secondary"
                size="xs"
                onClick={handleUnstageSelection}
                title="Unstage selected files"
              >
                <Minus className="size-3" />
                Unstage
              </Button>
            }
            generalActions={
              <Button
                variant="ghost"
                size="xs"
                disabled={!hasChanges}
                onClick={handleUnstageAll}
                title="Unstage all files"
              >
                <Minus className="size-3" />
                Unstage all
              </Button>
            }
          />
        )}
        <div className="min-h-0 flex-1 px-1">
          <ChangesListOrTree
            viewMode={viewMode}
            changes={changes}
            rootPath={workspace.path}
            isSelected={(path) => changesView.stagedSelection.has(path)}
            onToggleSelect={(path) => changesView.toggleStagedItem(path)}
            activePath={activePath}
            onSelectChange={handleSelectChange}
            onDoubleClickChange={handleDoubleClickChange}
            onPrefetch={(change) => prefetch(change.path)}
          />
        </div>
        {hasChanges && <CommitCard />}
      </div>
    </>
  );
});
