import { beforeEach, describe, expect, it, vi } from 'vitest';
import { browserSessionStore } from '@core/features/browser/api/browser/browser-session-store';
import { bindBrowserWebviewEvents } from './browser-webview-events';
import type { BrowserWebviewElement, BrowserWebviewEventMap } from './browser-webview-types';

class FakeBrowserWebview {
  url = 'about:blank';
  titleText = '';
  back = false;
  forward = false;
  readonly zoomFactors: number[] = [];
  readonly listeners = new Map<string, Set<(event: unknown) => void>>();

  canGoBack(): boolean {
    return this.back;
  }

  canGoForward(): boolean {
    return this.forward;
  }

  getURL(): string {
    return this.url;
  }

  getTitle(): string {
    return this.titleText;
  }

  setZoomFactor(factor: number): void {
    this.zoomFactors.push(factor);
  }

  addEventListener<K extends keyof BrowserWebviewEventMap>(
    type: K,
    listener: (event: BrowserWebviewEventMap[K]) => void
  ): void {
    const listeners = this.listeners.get(type) ?? new Set<(event: unknown) => void>();
    listeners.add(listener as (event: unknown) => void);
    this.listeners.set(type, listeners);
  }

  removeEventListener<K extends keyof BrowserWebviewEventMap>(
    type: K,
    listener: (event: BrowserWebviewEventMap[K]) => void
  ): void {
    this.listeners.get(type)?.delete(listener as (event: unknown) => void);
  }

  emit(type: keyof BrowserWebviewEventMap, event: unknown = {}): void {
    for (const listener of this.listeners.get(type) ?? []) {
      listener(event);
    }
  }
}

function asWebview(fake: FakeBrowserWebview): BrowserWebviewElement {
  return fake as unknown as BrowserWebviewElement;
}

describe('bindBrowserWebviewEvents', () => {
  beforeEach(() => {
    vi.useRealTimers();
    browserSessionStore.clear();
  });

  it('updates browser session state from webview events', () => {
    const session = browserSessionStore.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
    });
    const webview = new FakeBrowserWebview();
    webview.url = 'https://example.com/';
    webview.titleText = 'Example';
    webview.back = true;

    bindBrowserWebviewEvents(session.browserId, asWebview(webview));
    browserSessionStore.updateSession(session.browserId, { zoomFactor: 1.25 });

    expect(browserSessionStore.getSession(session.browserId)).toMatchObject({
      currentUrl: 'about:blank',
      title: '',
      canGoBack: false,
      canGoForward: false,
    });

    webview.emit('dom-ready');
    expect(webview.zoomFactors).toEqual([1.25]);

    expect(browserSessionStore.getSession(session.browserId)).toMatchObject({
      currentUrl: 'https://example.com/',
      title: 'Example',
      canGoBack: true,
      canGoForward: false,
    });

    webview.emit('did-start-loading');
    expect(browserSessionStore.getSession(session.browserId)?.isLoading).toBe(true);

    webview.emit('did-navigate', { url: 'https://example.com/docs' });
    expect(webview.zoomFactors).toEqual([1.25, 1.25]);
    expect(browserSessionStore.getSession(session.browserId)).toMatchObject({
      currentUrl: 'https://example.com/docs',
      loadError: undefined,
    });

    webview.emit('page-title-updated', { title: 'Docs' });
    webview.emit('page-favicon-updated', { favicons: ['https://example.com/favicon.ico'] });
    webview.emit('console-message', {
      level: 3,
      message: 'Unhandled error token=secret',
      line: 42,
      sourceId: 'https://example.com/app.js',
    });
    expect(browserSessionStore.getSession(session.browserId)).toMatchObject({
      title: 'Docs',
      faviconUrl: 'https://example.com/favicon.ico',
    });

    webview.emit('did-start-loading');
    expect(browserSessionStore.getSession(session.browserId)?.faviconUrl).toBeUndefined();

    webview.emit('did-fail-load', {
      errorCode: -105,
      errorDescription: 'Name not resolved',
      validatedURL: 'https://missing.invalid/',
    });
    expect(browserSessionStore.getSession(session.browserId)).toMatchObject({
      isLoading: false,
      loadError: {
        code: -105,
        description: 'Name not resolved',
        url: 'https://missing.invalid/',
      },
    });
  });

  it('reapplies the session zoom after navigation commits', () => {
    const session = browserSessionStore.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
    });
    browserSessionStore.updateSession(session.browserId, { zoomFactor: 1.5 });
    const webview = new FakeBrowserWebview();

    bindBrowserWebviewEvents(session.browserId, asWebview(webview));
    webview.emit('dom-ready');
    webview.emit('did-navigate', { url: 'https://example.com/' });
    webview.emit('did-stop-loading');

    expect(webview.zoomFactors).toEqual([1.5, 1.5, 1.5]);
  });

  it('removes listeners when disposed', () => {
    const session = browserSessionStore.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
    });
    const webview = new FakeBrowserWebview();
    const dispose = bindBrowserWebviewEvents(session.browserId, asWebview(webview));

    dispose();
    webview.emit('dom-ready');
    webview.emit('did-start-loading');

    expect(browserSessionStore.getSession(session.browserId)?.isLoading).toBe(false);
  });

  it('does not read webview state before dom-ready', () => {
    const session = browserSessionStore.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
    });
    const webview = new FakeBrowserWebview();
    webview.getURL = () => {
      throw new Error('not ready');
    };

    bindBrowserWebviewEvents(session.browserId, asWebview(webview));
    webview.emit('did-stop-loading');
    webview.emit('did-navigate', { url: 'https://example.com/' });

    expect(browserSessionStore.getSession(session.browserId)).toMatchObject({
      currentUrl: 'about:blank',
      title: '',
    });
  });

  it('refreshes history state after navigation commits', async () => {
    vi.useFakeTimers();
    const session = browserSessionStore.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
    });
    const webview = new FakeBrowserWebview();
    webview.url = 'https://example.com/';

    bindBrowserWebviewEvents(session.browserId, asWebview(webview));
    webview.emit('dom-ready');
    webview.emit('did-navigate', { url: 'https://example.com/docs' });
    expect(browserSessionStore.getSession(session.browserId)?.canGoBack).toBe(false);

    webview.url = 'https://example.com/docs';
    webview.back = true;
    await vi.runOnlyPendingTimersAsync();

    expect(browserSessionStore.getSession(session.browserId)).toMatchObject({
      currentUrl: 'https://example.com/docs',
      canGoBack: true,
    });
  });

  it('refreshes history state when Electron updates navigation entries after load events', async () => {
    vi.useFakeTimers();
    const session = browserSessionStore.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
    });
    const webview = new FakeBrowserWebview();
    webview.url = 'https://example.com/';

    bindBrowserWebviewEvents(session.browserId, asWebview(webview));
    webview.emit('dom-ready');
    webview.emit('did-navigate', { url: 'https://example.com/docs' });
    webview.url = 'https://example.com/docs';
    webview.emit('did-stop-loading');

    await vi.advanceTimersByTimeAsync(0);
    expect(browserSessionStore.getSession(session.browserId)?.canGoBack).toBe(false);

    webview.back = true;
    await vi.advanceTimersByTimeAsync(50);

    expect(browserSessionStore.getSession(session.browserId)).toMatchObject({
      currentUrl: 'https://example.com/docs',
      canGoBack: true,
    });
  });
});
