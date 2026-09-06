import { EmptyState, WorkspaceIcon } from '@emdash/ui/react/components';
import {
  CollectionToolbar,
  CollectionView,
  CollectionViewCell,
  useQueryListSource,
  type CollectionViewColumn,
} from '@emdash/ui/react/patterns';
import { Button, RelativeTime } from '@emdash/ui/react/primitives';
import { PlusIcon } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { useState } from 'react';
import type { WorkspacesScope } from '@core/features/workspaces/api/browser/use-workspace-groups';
import { useWorkspaceRows } from '@core/features/workspaces/api/browser/use-workspace-rows';
import { WorkspacesOfflineState } from '@core/features/workspaces/contributions/browser/workspace-states';
import { useOpenModal } from '@core/manifests/browser/modal-api';
import {
  buildWorkspaceItems,
  createWorkspacesListView,
  type WorkspacesListItem,
  type WorkspacesListViewModel,
} from './workspaces-list-model';

const WORKSPACE_COLUMNS: CollectionViewColumn<WorkspacesListItem>[] = [
  {
    id: 'icon',
    width: '2.25rem',
    cell: (item) => <WorkspaceIcon type={item.kind} status={item.status} />,
  },
  {
    id: 'name',
    width: 'minmax(0, 1fr)',
    cell: (item) => <CollectionViewCell primary={item.name} secondary={item.path} />,
  },
  {
    id: 'worktrees',
    width: '10rem',
    cell: (item) => (
      <CollectionViewCell
        primary={formatCount(item.worktreeCount, 'Worktree')}
        secondary={formatCount(item.linkedTaskCount, 'linked task')}
      />
    ),
  },
  {
    id: 'usage',
    width: '10rem',
    cell: (item) => (
      <CollectionViewCell
        primary={item.lastActivityAt ? <RelativeTime value={item.lastActivityAt} /> : 'Never'}
        secondary={formatCount(item.activeTaskCount, 'Task active', 'Tasks active')}
      />
    ),
  },
];

/**
 * One row per project, rendered through CollectionView in state mode; clicking
 * a row opens the project's workspace detail. Serves both the Local Workspaces
 * tab and the machine details Workspaces section.
 */
export const WorkspacesListView = observer(function WorkspacesListView({
  scope,
  openDetail,
  enabled = true,
}: {
  scope: WorkspacesScope;
  openDetail: (projectId: string) => void;
  /** Gates the workspace query, e.g. on remote server usability. */
  enabled?: boolean;
}) {
  const openAddProject = useOpenModal('addProjectModal');
  const workspaceRows = useWorkspaceRows({ scope, enabled });
  const { workspaceQuery, groups } = workspaceRows;

  // `groups` is derived from the query plus usage joins, so it stands in for
  // the query's data; loading/error still come from the query itself.
  const source = useQueryListSource(
    {
      data: groups,
      isLoading: workspaceQuery.isLoading,
      isError: workspaceQuery.isError,
      error: workspaceQuery.error,
    },
    buildWorkspaceItems
  );
  const [view] = useState(() => createWorkspacesListView(source));

  if (scope.kind === 'machine' && !enabled) {
    return (
      <WorkspacesOfflineState description="Workspaces load when the machine reconnects and its workspace server is healthy." />
    );
  }

  return (
    <view.Root>
      <CollectionView
        view={view}
        columns={WORKSPACE_COLUMNS}
        toolbar={
          <WorkspacesToolbar
            view={view}
            onAddProject={() =>
              void openAddProject(
                scope.kind === 'machine'
                  ? { strategy: 'ssh', mode: 'clone', connectionId: scope.machineId }
                  : { strategy: 'local', mode: 'pick' }
              )
            }
          />
        }
        onItemClick={(item) => openDetail(item.id)}
        errorSlot={
          <EmptyState
            bare
            label="Could not load workspaces."
            description={errorMessage(workspaceQuery.error)}
          />
        }
        emptySlot={<WorkspacesEmpty view={view} />}
      />
    </view.Root>
  );
});

const WorkspacesToolbar = observer(function WorkspacesToolbar({
  view,
  onAddProject,
}: {
  view: WorkspacesListViewModel;
  onAddProject: () => void;
}) {
  const search = view.useSearch();
  return (
    <CollectionToolbar
      searchValue={search.query}
      onSearchValueChange={search.setQuery}
      searchPlaceholder="Search workspaces…"
      actions={
        <Button type="button" variant="primary" onClick={onAddProject}>
          <PlusIcon />
          Add Project
        </Button>
      }
    />
  );
});

const WorkspacesEmpty = observer(function WorkspacesEmpty({
  view,
}: {
  view: WorkspacesListViewModel;
}) {
  const search = view.useSearch();
  return (
    <EmptyState
      bare
      label={
        search.query.trim().length > 0 ? 'No workspaces match your search.' : 'No workspaces found.'
      }
    />
  );
});

function formatCount(count: number, singular: string, plural = `${singular}s`) {
  return `${count} ${count === 1 ? singular : plural}`;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}
