import { describe, expect, it } from 'vitest';
import { taskDiffSelectionSchema, taskPaneLayoutMemento, taskPaneLayoutSchema } from './mementos';

describe('task pane layout memento', () => {
  it('uses a safe one-pane default', () => {
    expect(taskPaneLayoutMemento.default.groups).toHaveLength(1);
    expect(taskPaneLayoutSchema.safeParse(taskPaneLayoutMemento.default).status).toBe('ok');
  });

  it('rejects layouts without a pane', () => {
    expect(
      taskPaneLayoutSchema.safeParse({
        version: '2',
        groups: [],
        activeGroupId: '',
      }).status
    ).toBe('invalid');
  });

  it('upgrades a v1 document by dropping the abandoned paneSizes', () => {
    const result = taskPaneLayoutSchema.safeParse({
      version: '1',
      groups: [{ groupId: 'a', tabManager: { tabs: [] } }],
      activeGroupId: 'a',
      paneSizes: [100],
    });
    expect(result.status).toBe('ok');
    if (result.status === 'ok') {
      expect(result.data).toEqual({
        version: '2',
        groups: [{ groupId: 'a', tabManager: { tabs: [] } }],
        activeGroupId: 'a',
      });
    }
  });

  it('rejects absolute diff-tab paths', () => {
    const result = taskPaneLayoutSchema.safeParse({
      version: '2',
      groups: [
        {
          groupId: 'a',
          tabManager: {
            tabs: [
              {
                kind: 'diff',
                tabId: 'diff-1',
                path: '/repo/src/index.ts',
                diffGroup: 'disk',
                originalRef: { kind: 'commit', sha: 'HEAD' },
                isPreview: false,
              },
            ],
            activeTabId: 'diff-1',
          },
        },
      ],
      activeGroupId: 'a',
    });

    expect(result.status).toBe('invalid');
  });

  it('round-trips a CAD artifact tab in a split chat and artifact layout', () => {
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
    const value = {
      version: '2' as const,
      groups: [
        {
          groupId: 'chat',
          tabManager: {
            tabs: [
              {
                kind: 'acp-chat' as const,
                tabId: 'chat-1',
                conversationId: 'conversation-1',
                isPreview: false,
              },
            ],
            activeTabId: 'chat-1',
          },
        },
        {
          groupId: 'artifact',
          tabManager: {
            tabs: [
              {
                kind: 'cad' as const,
                tabId: 'cad-1',
                path: 'parts/part.step',
                workspacePath: '/tmp/workspace',
                browserId: 'browser-1',
                session,
                chatOpen: false,
                workspaceMode: '3d' as const,
                isPreview: false,
              },
            ],
            activeTabId: 'cad-1',
          },
        },
      ],
      activeGroupId: 'artifact',
    };

    const result = taskPaneLayoutSchema.safeParse(value);
    expect(result.status).toBe('ok');
    if (result.status === 'ok') expect(result.data).toEqual(value);
  });
});

describe('task diff selection memento', () => {
  it('rejects absolute active diff paths', () => {
    const result = taskDiffSelectionSchema.safeParse({
      version: '1',
      activeFile: {
        path: '/repo/src/index.ts',
        type: 'disk',
        group: 'disk',
        originalRef: { kind: 'commit', sha: 'HEAD' },
      },
    });

    expect(result.status).toBe('invalid');
  });
});
