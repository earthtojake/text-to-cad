import { observable, runInAction } from 'mobx';
import { describe, expect, it } from 'vitest';
import type { WorkspaceRowsGroup } from '@core/features/workspaces/api/browser/use-workspace-rows';
import type { ProjectWorkspaceRow } from '@core/primitives/workspaces/api';
import {
  buildWorkspaceItems,
  createWorkspacesListView,
  type WorkspacesListItem,
} from './workspaces-list-model';

describe('buildWorkspaceItems', () => {
  it('aggregates one item per project from the root row and its worktrees', () => {
    const items = buildWorkspaceItems([
      group('project-1', 'Emdash', [
        joined(workspaceRow({ kind: 'root', path: '/repo', workspaceId: 'root-1' })),
        joined(
          workspaceRow({
            path: '/repo/task-a',
            workspaceId: 'ws-a',
            tasks: [task(), task()],
            lastActivityAt: '2026-08-01T00:00:00.000Z',
          })
        ),
        joined(
          workspaceRow({
            path: '/repo/task-b',
            workspaceId: 'ws-b',
            tasks: [task()],
            lastActivityAt: '2026-08-09T00:00:00.000Z',
          }),
          'active'
        ),
      ]),
    ]);

    expect(items).toEqual([
      {
        id: 'project-1',
        name: 'Emdash',
        path: '/repo',
        kind: 'repository',
        status: 'active',
        worktreeCount: 2,
        linkedTaskCount: 3,
        lastActivityAt: '2026-08-09T00:00:00.000Z',
        activeTaskCount: 1,
      },
    ]);
  });

  it('falls back to the first row and project name when no root row exists', () => {
    const items = buildWorkspaceItems([
      group('project-1', 'Emdash', [joined(workspaceRow({ path: '/repo/task-a' }))]),
      group('project-2', 'Empty', []),
    ]);

    expect(items[0]).toMatchObject({ path: '/repo/task-a', worktreeCount: 1 });
    expect(items[1]).toMatchObject({ path: 'Empty', status: 'idle', lastActivityAt: undefined });
  });
});

describe('createWorkspacesListView', () => {
  it('re-derives from the reactive getter and searches name and path', () => {
    const box = observable.box<WorkspacesListItem[]>([], { deep: false });
    const view = createWorkspacesListView({ kind: 'sync', items: () => box.get() });
    const store = view.store;

    expect(store.visibleItems).toEqual([]);

    runInAction(() =>
      box.set([item('a', 'Emdash', '/repos/emdash'), item('b', 'Docs', '/repos/docs')])
    );
    expect(store.visibleItems.map((entry) => entry.id)).toEqual(['a', 'b']);

    store.search!.setQuery('emd');
    expect(store.visibleItems.map((entry) => entry.id)).toEqual(['a']);

    store.search!.setQuery('/repos/docs');
    expect(store.visibleItems.map((entry) => entry.id)).toEqual(['b']);

    store.search!.setQuery('nothing-matches');
    expect(store.visibleItems).toEqual([]);
  });
});

function item(id: string, name: string, path: string): WorkspacesListItem {
  return {
    id,
    name,
    path,
    kind: 'repository',
    status: 'idle',
    worktreeCount: 0,
    linkedTaskCount: 0,
    activeTaskCount: 0,
  };
}

function group(
  id: string,
  name: string,
  workspaces: WorkspaceRowsGroup['workspaces']
): WorkspaceRowsGroup {
  return {
    project: { id, name } as WorkspaceRowsGroup['project'],
    warnings: [],
    workspaces,
  };
}

function joined(
  row: ProjectWorkspaceRow,
  status: WorkspaceRowsGroup['workspaces'][number]['status'] = 'idle'
): WorkspaceRowsGroup['workspaces'][number] {
  return {
    row,
    key: row.workspaceId ?? row.path,
    status,
    pendingRemoval: false,
    removalNeedsAttention: false,
  };
}

function workspaceRow(overrides: Partial<ProjectWorkspaceRow> = {}): ProjectWorkspaceRow {
  return {
    kind: 'workspace',
    projectId: 'project-1',
    workspaceId: null,
    path: '/repo/task',
    branch: 'task',
    tasks: [],
    usage: null,
    gitStats: null,
    pathState: 'measured',
    canCleanArtifacts: true,
    canDelete: true,
    hasActiveSessions: false,
    pendingRemoval: false,
    errors: [],
    ...overrides,
  } as ProjectWorkspaceRow;
}

function task(): ProjectWorkspaceRow['tasks'][number] {
  return {
    taskId: 'task-1',
    name: 'Task',
    status: 'in_progress',
    updatedAt: '2026-08-01T00:00:00.000Z',
  };
}
