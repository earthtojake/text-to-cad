import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { browserSessionStore } from '@core/features/browser/api/browser/browser-session-store';
import { BrowserPane } from './browser-pane';

const browserRpc = vi.hoisted(() => ({
  bindWebContents: vi.fn(),
  registerSession: vi.fn(),
  releaseWebContents: vi.fn(),
  setActiveBrowser: vi.fn(),
}));
const paneVisibility = vi.hoisted(() => ({ current: true }));

vi.mock('@core/features/workbench/api/browser/task-composition-context', () => ({}));

vi.mock('@core/primitives/workbench-shell/browser/tabs/pane-context', () => ({
  usePaneContext: () => ({
    pane: {
      get isVisible() {
        return paneVisibility.current;
      },
      setNextTabActive: vi.fn(),
      setPreviousTabActive: vi.fn(),
    },
  }),
}));

vi.mock('@core/features/browser/api/browser/client', () => ({
  getBrowserClient: async () => browserRpc,
}));

vi.mock('@core/primitives/desktop-host/browser/host-client', () => ({
  getHostClient: async () => ({
    events: {
      subscribe: vi.fn(async () => () => {}),
    },
  }),
}));

vi.mock('./browser-toolbar', async () => {
  const React = await import('react');
  return {
    BrowserToolbar: ({ onNavigate }: { onNavigate?: (url: string) => boolean }) =>
      React.createElement('button', { onClick: () => onNavigate?.('https://linkedin.com/') }),
  };
});

describe('BrowserPane', () => {
  let dom: JSDOM;
  let root: Root;
  let container: HTMLElement;

  beforeEach(() => {
    dom = new JSDOM('<div id="root"></div>');
    vi.stubGlobal('window', dom.window);
    vi.stubGlobal('document', dom.window.document);
    vi.stubGlobal('HTMLElement', dom.window.HTMLElement);
    vi.stubGlobal('Element', dom.window.Element);
    vi.stubGlobal('Node', dom.window.Node);
    vi.stubGlobal('Event', dom.window.Event);
    vi.stubGlobal('MouseEvent', dom.window.MouseEvent);
    vi.stubGlobal('IS_REACT_ACT_ENVIRONMENT', true);
    container = dom.window.document.getElementById('root')!;
    root = createRoot(container);
    browserSessionStore.clear();
    browserRpc.registerSession.mockResolvedValue({ success: true });
    paneVisibility.current = true;
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    await Promise.resolve();
    browserSessionStore.clear();
    vi.clearAllMocks();
    vi.unstubAllGlobals();
    dom.window.close();
  });

  it('does not load the submitted URL twice when the webview becomes ready', async () => {
    const session = browserSessionStore.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
    });

    await act(async () => {
      root.render(
        React.createElement(BrowserPane, { browserId: session.browserId, visible: true })
      );
    });
    await act(async () => {
      container.querySelector('button')?.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    });

    const webview = container.querySelector<HTMLElement>('webview')!;
    const loadURL = vi.fn();
    Object.assign(webview, {
      canGoBack: () => false,
      canGoForward: () => false,
      getTitle: () => 'LinkedIn',
      getURL: () => webview.getAttribute('src'),
      getWebContentsId: () => 123,
      loadURL,
      setZoomFactor: vi.fn(),
    });

    await act(async () => webview.dispatchEvent(new dom.window.Event('dom-ready')));

    expect(webview.getAttribute('src')).toBe('https://linkedin.com/');
    expect(loadURL).not.toHaveBeenCalled();
  });

  it('unmounts a guest in an inactive task even when its tab remains active', async () => {
    const session = browserSessionStore.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
      initialUrl: 'https://example.com/',
    });

    paneVisibility.current = false;
    await act(async () => {
      root.render(
        React.createElement(BrowserPane, { browserId: session.browserId, visible: true })
      );
    });

    expect(container.querySelector('webview')).toBeNull();
    expect(browserRpc.releaseWebContents).toHaveBeenCalledWith({ browserId: session.browserId });

    paneVisibility.current = true;
    await act(async () => {
      root.render(
        React.createElement(BrowserPane, {
          key: 'active-task',
          browserId: session.browserId,
          visible: true,
        })
      );
    });

    const activeWebview = container.querySelector<HTMLElement>('webview')!;
    expect(activeWebview.hidden).toBe(false);
    expect(activeWebview.style.display).toBe('flex');
    expect(activeWebview.style.width).toBe('100%');
    expect(activeWebview.style.height).toBe('100%');
  });

  it('keeps an inactive tab mounted at zero bounds without releasing its guest', async () => {
    const session = browserSessionStore.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
      initialUrl: 'https://example.com/',
    });

    await act(async () => {
      root.render(
        React.createElement(BrowserPane, { browserId: session.browserId, visible: false })
      );
    });

    const hiddenWebview = container.querySelector<HTMLElement>('webview')!;
    expect(hiddenWebview).not.toBeNull();
    expect(hiddenWebview.hidden).toBe(true);
    expect(hiddenWebview.getAttribute('aria-hidden')).toBe('true');
    expect(hiddenWebview.style.display).toBe('none');
    expect(hiddenWebview.style.visibility).toBe('hidden');
    expect(hiddenWebview.style.width).toBe('0px');
    expect(hiddenWebview.style.height).toBe('0px');
    expect(browserRpc.releaseWebContents).not.toHaveBeenCalled();
  });

  it('remounts a released task guest at the session latest URL', async () => {
    const session = browserSessionStore.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
      initialUrl: 'https://example.com/original',
    });

    await act(async () => {
      root.render(
        React.createElement(BrowserPane, { browserId: session.browserId, visible: true })
      );
    });
    expect(container.querySelector('webview')?.getAttribute('src')).toBe(
      'https://example.com/original'
    );

    await act(async () => {
      browserSessionStore.updateSession(session.browserId, {
        currentUrl: 'https://example.com/latest',
      });
      paneVisibility.current = false;
      root.render(
        React.createElement(BrowserPane, { browserId: session.browserId, visible: false })
      );
    });
    expect(container.querySelector('webview')).toBeNull();

    paneVisibility.current = true;
    await act(async () => {
      root.render(
        React.createElement(BrowserPane, { browserId: session.browserId, visible: true })
      );
    });
    expect(container.querySelector('webview')?.getAttribute('src')).toBe(
      'https://example.com/latest'
    );
  });

  it('renders a minimal load error state', async () => {
    const session = browserSessionStore.createSession({
      browserId: 'browser-1',
      projectId: 'project-1',
      workspaceId: 'workspace-1',
      taskId: 'task-1',
      initialUrl: 'https://missing.invalid/',
    });
    browserSessionStore.updateSession(session.browserId, {
      isLoading: false,
      loadError: {
        code: -105,
        description: 'net::ERR_NAME_NOT_RESOLVED',
        url: 'https://missing.invalid/',
      },
    });

    await act(async () => {
      root.render(
        React.createElement(BrowserPane, { browserId: session.browserId, visible: true })
      );
    });

    expect(container.querySelector('h1')?.textContent).toBe("This site can't be reached");
    expect(container.querySelector('p')?.textContent).toBe(
      "missing.invalid's server IP address could not be found. (ERR_NAME_NOT_RESOLVED)"
    );
    expect(container.textContent).not.toContain('Try:');
    expect(
      Array.from(container.querySelectorAll('button'))
        .map((button) => button.textContent)
        .filter(Boolean)
    ).toEqual(['Reload', 'Open externally']);
  });
});
