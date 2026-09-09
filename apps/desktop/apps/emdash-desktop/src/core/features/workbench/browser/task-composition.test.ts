import { describe, expect, it, vi } from 'vitest';
import { portablePath } from '@core/primitives/desktop-runtime/api';
import {
  deleteSplitPaneLayoutEntries,
  resolvePaneLayoutFilePaths,
  sanitizeDiffSelection,
} from './task-composition-state';

describe('task composition diff selection hydration', () => {
  it('keeps a valid working-tree selection', () => {
    expect(
      sanitizeDiffSelection(
        {
          version: '1',
          activeFile: {
            path: portablePath('src/index.ts'),
            type: 'disk',
            group: 'disk',
            originalRef: { kind: 'commit', sha: 'HEAD' },
          },
        },
        new Set(['src/index.ts'])
      ).activeFile?.path
    ).toBe('src/index.ts');
  });

  it('drops a stale persisted working-tree selection', () => {
    expect(
      sanitizeDiffSelection(
        {
          version: '1',
          activeFile: {
            path: portablePath('deleted.ts'),
            type: 'disk',
            group: 'disk',
            originalRef: { kind: 'commit', sha: 'HEAD' },
          },
        },
        new Set()
      ).activeFile
    ).toBeUndefined();
  });

  it('keeps commit and PR selections without working-tree validation', () => {
    for (const group of ['git', 'pr'] as const) {
      const result = sanitizeDiffSelection(
        {
          version: '1',
          activeFile: {
            path: portablePath('src/index.ts'),
            type: 'git',
            group,
            originalRef: { kind: 'commit', sha: 'HEAD' },
          },
        },
        new Set()
      );
      expect(result.activeFile?.path).toBe('src/index.ts');
    }
  });
});

describe('task pane layout path hydration', () => {
  it('keeps file and CAD tabs absolute and diff tabs checkout-relative', () => {
    const session = {
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
      profileId: 'default',
      partition: 'persist:hardcore-browser-profile-default',
      currentUrl: 'about:blank',
      title: 'part.step',
      isLoading: false,
      canGoBack: false,
      canGoForward: false,
      zoomFactor: 1,
      createdAt: 1,
      updatedAt: 2,
    };
    const result = resolvePaneLayoutFilePaths(
      {
        version: '2',
        groups: [
          {
            groupId: 'default',
            tabManager: {
              tabs: [
                {
                  kind: 'file',
                  tabId: 'file-1',
                  path: 'src/file.ts',
                  isPreview: false,
                },
                {
                  kind: 'cad',
                  tabId: 'cad-1',
                  path: 'models/part.step',
                  workspacePath: '/tmp/workspace',
                  browserId: 'browser-1',
                  session,
                  chatOpen: false,
                  workspaceMode: '3d',
                  isPreview: false,
                },
                {
                  kind: 'diff',
                  tabId: 'diff-1',
                  path: portablePath('src/change.ts'),
                  diffGroup: 'disk',
                  originalRef: { kind: 'commit', sha: 'HEAD' },
                  isPreview: false,
                },
              ],
              activeTabId: 'diff-1',
            },
          },
        ],
        activeGroupId: 'default',
      },
      '/tmp/workspace'
    );

    expect(result.groups[0]?.tabManager.tabs).toEqual([
      {
        kind: 'file',
        tabId: 'file-1',
        path: '/tmp/workspace/src/file.ts',
        isPreview: false,
      },
      {
        kind: 'cad',
        tabId: 'cad-1',
        path: '/tmp/workspace/models/part.step',
        workspacePath: '/tmp/workspace',
        browserId: 'browser-1',
        session,
        chatOpen: false,
        workspaceMode: '3d',
        isPreview: false,
      },
      {
        kind: 'diff',
        tabId: 'diff-1',
        path: 'src/change.ts',
        diffGroup: 'disk',
        originalRef: { kind: 'commit', sha: 'HEAD' },
        isPreview: false,
      },
    ]);
  });
});

describe('split-pane layout cleanup on pane group destroy', () => {
  const paneA = '11111111-1111-4111-8111-111111111111';
  const paneB = '22222222-2222-4222-8222-222222222222';
  const paneC = '33333333-3333-4333-8333-333333333333';
  const entryKey = (...paneIds: string[]) =>
    `react-resizable-panels:task-main-split:${paneIds.map((id) => `pane:${id}`).join(':')}`;

  it('deletes every entry referencing the destroyed pane group and keeps the rest', () => {
    const deleteEntry = vi.fn();
    const keys = [
      entryKey(paneA, paneB),
      entryKey(paneA, paneB, paneC),
      entryKey(paneA, paneC),
      'react-resizable-panels:task-main-vertical:task-main-content:task-terminal-drawer',
    ];

    deleteSplitPaneLayoutEntries({ deleteEntry }, keys, paneB);

    expect(deleteEntry.mock.calls.map(([key]) => key)).toEqual([
      entryKey(paneA, paneB),
      entryKey(paneA, paneB, paneC),
    ]);
  });

  it('is a no-op when no entry references the pane group', () => {
    const deleteEntry = vi.fn();

    deleteSplitPaneLayoutEntries(
      { deleteEntry },
      [entryKey(paneA, paneB), 'react-resizable-panels:workspace-outer'],
      paneC
    );

    expect(deleteEntry).not.toHaveBeenCalled();
  });
});
