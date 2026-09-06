import { describe, expect, it } from 'vitest';
import { BrowserSessionStore } from '@core/features/browser/api/browser/browser-session-store';

describe('BrowserSessionStore', () => {
  it('creates isolated sessions with normalized initial URLs', () => {
    const store = new BrowserSessionStore();

    const session = store.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
      initialUrl: 'localhost:5173',
    });

    expect(session.currentUrl).toBe('http://localhost:5173/');
    expect(session.profileId).toBe('default');
    expect(session.partition).toBe('persist:hardcore-browser-profile');
    expect(store.getSession('browser-1')).toEqual(session);
  });

  it('updates mutable browser state while preserving URL on rejected navigation', () => {
    const store = new BrowserSessionStore();
    store.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
      initialUrl: 'https://example.com',
    });

    const updated = store.updateSession('browser-1', {
      currentUrl: 'javascript:alert(1)',
      title: 'Example',
      canGoBack: true,
    });

    expect(updated).toMatchObject({
      currentUrl: 'https://example.com/',
      title: 'Example',
      canGoBack: true,
    });
  });

  it('clears favicon state explicitly', () => {
    const store = new BrowserSessionStore();
    store.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
    });

    store.updateSession('browser-1', { faviconUrl: 'https://example.com/favicon.ico' });
    store.updateSession('browser-1', { faviconUrl: null });

    expect(store.getSession('browser-1')?.faviconUrl).toBeUndefined();
  });

  it('restores sessions onto their profile partition and clears transient load state', () => {
    const store = new BrowserSessionStore();

    store.restoreSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
      profileId: 'work',
      partition: 'persist:wrong',
      currentUrl: 'example.com',
      title: 'Example',
      isLoading: true,
      canGoBack: true,
      canGoForward: false,
      loadError: { description: 'stale failure' },
      createdAt: 100,
      updatedAt: 100,
    });

    expect(store.getSession('browser-1')).toMatchObject({
      profileId: 'work',
      partition: 'persist:hardcore-browser-profile-work',
      currentUrl: 'https://example.com/',
      isLoading: false,
      loadError: undefined,
    });
  });

  it('falls back to the default profile when restoring invalid profile ids', () => {
    const store = new BrowserSessionStore();

    store.restoreSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
      profileId: '../not-safe',
      partition: 'persist:wrong',
      currentUrl: 'about:blank',
      title: '',
      isLoading: false,
      canGoBack: false,
      canGoForward: false,
      createdAt: 100,
      updatedAt: 100,
    });

    expect(store.getSession('browser-1')).toMatchObject({
      profileId: 'default',
      partition: 'persist:hardcore-browser-profile',
    });
  });

  it('falls back to the first available profile when restoring deleted profile ids', () => {
    const store = new BrowserSessionStore();

    store.restoreSession(
      {
        browserId: 'browser-1',
        projectId: 'project-1',
        workspaceId: 'workspace-1',
        taskId: 'task-1',
        profileId: 'work',
        partition: 'persist:wrong',
        currentUrl: 'about:blank',
        title: '',
        isLoading: false,
        canGoBack: false,
        canGoForward: false,
        createdAt: 100,
        updatedAt: 100,
      },
      [{ id: 'personal', name: 'Personal' }]
    );

    expect(store.getSession('browser-1')).toMatchObject({
      profileId: 'personal',
      partition: 'persist:hardcore-browser-profile-personal',
    });
  });

  it('switches a session onto another profile partition', () => {
    const store = new BrowserSessionStore();
    store.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
      initialUrl: 'https://example.com',
    });
    store.updateSession('browser-1', {
      isLoading: true,
      loadError: { description: 'stale failure' },
    });

    const switched = store.setSessionProfile('browser-1', 'work', [
      { id: 'default', name: 'Default' },
      { id: 'work', name: 'Work' },
    ]);

    expect(switched).toMatchObject({
      profileId: 'work',
      partition: 'persist:hardcore-browser-profile-work',
      currentUrl: 'https://example.com/',
      isLoading: false,
      loadError: undefined,
    });
    expect(store.getSession('browser-1')).toEqual(switched);
  });

  it('switches sessions to isolated per-task partitions and back', () => {
    const store = new BrowserSessionStore();
    store.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
    });

    store.setSessionProfile('browser-1', 'isolated-per-task');
    expect(store.getSession('browser-1')).toMatchObject({
      profileId: 'isolated-per-task',
      partition: 'persist:hardcore-browser-isolated-project-1-workspace-1-task-1',
    });

    store.setSessionProfile('browser-1', 'default');
    expect(store.getSession('browser-1')).toMatchObject({
      profileId: 'default',
      partition: 'persist:hardcore-browser-profile',
    });
  });

  it('ignores profile switches to unknown profiles or sessions', () => {
    const store = new BrowserSessionStore();
    const session = store.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
    });

    expect(store.setSessionProfile('missing', 'work')).toBeNull();
    expect(
      store.setSessionProfile('browser-1', 'work', [{ id: 'default', name: 'Default' }])
    ).toMatchObject({ profileId: 'default' });
    expect(store.getSession('browser-1')).toEqual(session);
  });

  it('migrates active sessions away from deleted profiles', () => {
    const store = new BrowserSessionStore();
    store.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
      profileId: 'work',
    });

    store.migrateProfileSessions('work', 'personal', [
      { id: 'default', name: 'Default' },
      { id: 'personal', name: 'Personal' },
    ]);

    expect(store.getSession('browser-1')).toMatchObject({
      profileId: 'personal',
      partition: 'persist:hardcore-browser-profile-personal',
    });
  });

  it('removes sessions explicitly', () => {
    const store = new BrowserSessionStore();
    store.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
    });

    store.removeSession('browser-1');

    expect(store.getSession('browser-1')).toBeUndefined();
  });
});
