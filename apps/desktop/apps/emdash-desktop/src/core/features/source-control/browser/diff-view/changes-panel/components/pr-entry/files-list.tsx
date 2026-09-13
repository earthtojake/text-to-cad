import type { GitChange } from '@emdash/core/runtimes/git/api';
import { observer } from 'mobx-react-lite';
import {
  useTaskComposition,
  useWorkspace,
} from '@core/features/workbench/api/browser/task-composition-context';
import { commitRef, refsEqual } from '@core/primitives/git/api';
import { getPrNumber, type PullRequest } from '@core/services/pull-requests/api';
import { activeDiffEntry } from '../../../pane-selectors';
import { useChangesViewMode } from '../../hooks/use-changes-view-mode';
import { usePrefetchDiffModels } from '../../hooks/use-prefetch-diff-models';
import { ChangesListOrTree } from '../changes-list-or-tree';

export const PrFilesList = observer(function PrFilesList({ pr }: { pr: PullRequest }) {
  const workspace = useWorkspace();
  const taskView = useTaskComposition();
  const prStore = taskView.prStore!;
  const { mode: viewMode } = useChangesViewMode('pr');

  const prNumber = getPrNumber(pr) ?? undefined;
  const baseRef = commitRef(pr.baseRefOid);
  const modifiedRef = commitRef(pr.headRefOid);
  const prFiles = prStore.getFiles(pr).data ?? [];

  const prefetchPrDiff = usePrefetchDiffModels('pr', baseRef, modifiedRef);

  const _activeDiff = activeDiffEntry(taskView.activePane);
  const activePath =
    _activeDiff?.diffGroup === 'pr' &&
    _activeDiff.prNumber === prNumber &&
    refsEqual(_activeDiff.originalRef, baseRef) &&
    refsEqual(_activeDiff.modifiedRef ?? modifiedRef, modifiedRef)
      ? _activeDiff.path
      : undefined;

  const handleSelectChange = (change: GitChange) => {
    taskView.activePane.open(
      'diff',
      {
        activeFile: {
          path: change.path,
          type: 'git',
          group: 'pr',
          originalRef: baseRef,
          modifiedRef,
          prNumber,
          prBaseOid: pr.baseRefOid,
          prHeadOid: pr.headRefOid,
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
          group: 'pr',
          originalRef: baseRef,
          modifiedRef,
          prNumber,
          prBaseOid: pr.baseRefOid,
          prHeadOid: pr.headRefOid,
        },
        status: change.status,
      },
      { preview: false }
    );
  };

  return (
    <ChangesListOrTree
      viewMode={viewMode}
      className="py-3"
      changes={prFiles}
      rootPath={workspace.path}
      activePath={activePath}
      onSelectChange={handleSelectChange}
      onDoubleClickChange={handleDoubleClickChange}
      onPrefetch={(change) => prefetchPrDiff(change.path)}
    />
  );
});
