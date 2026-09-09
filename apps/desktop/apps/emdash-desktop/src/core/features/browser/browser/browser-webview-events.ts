import { browserSessionStore } from '@core/features/browser/api/browser/browser-session-store';
import { BROWSER_DEFAULT_URL, normalizeBrowserZoomFactor } from '@core/primitives/browser/api';
import type { BrowserWebviewElement } from './browser-webview-types';

export function bindBrowserWebviewEvents(
  browserId: string,
  webview: BrowserWebviewElement,
  options: { onDomReady?: () => void } = {}
): () => void {
  let isDomReady = false;
  const historySyncTimers = new Set<ReturnType<typeof setTimeout>>();

  const syncHistoryState = () => {
    if (!isDomReady) return;
    const currentUrl = webview.getURL() || BROWSER_DEFAULT_URL;
    browserSessionStore.updateSession(browserId, {
      currentUrl,
      title: webview.getTitle(),
      canGoBack: webview.canGoBack(),
      canGoForward: webview.canGoForward(),
    });
  };

  const scheduleHistoryStateSync = () => {
    for (const timer of historySyncTimers) clearTimeout(timer);
    historySyncTimers.clear();

    for (const delay of [0, 50, 200]) {
      const timer = setTimeout(() => {
        historySyncTimers.delete(timer);
        syncHistoryState();
      }, delay);
      historySyncTimers.add(timer);
    }
  };

  const scheduleHistoryStateSyncOnce = () => {
    const timer = setTimeout(() => {
      historySyncTimers.delete(timer);
      syncHistoryState();
    }, 0);
    historySyncTimers.add(timer);
  };

  const applySessionZoom = () => {
    const session = browserSessionStore.getSession(browserId);
    if (session?.zoomFactor === undefined) return;
    webview.setZoomFactor(normalizeBrowserZoomFactor(session.zoomFactor));
  };

  const onDomReady = () => {
    isDomReady = true;
    applySessionZoom();
    syncHistoryState();
    options.onDomReady?.();
  };

  const onStartLoading = () => {
    browserSessionStore.updateSession(browserId, {
      faviconUrl: null,
      isLoading: true,
      loadError: null,
    });
  };

  const onStopLoading = () => {
    if (!isDomReady) return;
    const currentUrl = webview.getURL() || BROWSER_DEFAULT_URL;
    browserSessionStore.updateSession(browserId, {
      isLoading: false,
      currentUrl,
      title: webview.getTitle(),
      canGoBack: webview.canGoBack(),
      canGoForward: webview.canGoForward(),
    });
    applySessionZoom();
    scheduleHistoryStateSyncOnce();
  };

  const onNavigate = (event: { url: string }) => {
    if (!isDomReady) return;
    browserSessionStore.updateSession(browserId, {
      currentUrl: event.url,
      canGoBack: webview.canGoBack(),
      canGoForward: webview.canGoForward(),
      loadError: null,
    });
    applySessionZoom();
    scheduleHistoryStateSync();
  };

  const onFailLoad = (event: {
    errorCode: number;
    errorDescription: string;
    validatedURL: string;
  }) => {
    if (event.errorCode === -3) return;
    browserSessionStore.updateSession(browserId, {
      isLoading: false,
      loadError: {
        code: event.errorCode,
        description: event.errorDescription,
        url: event.validatedURL,
      },
    });
  };

  const onTitle = (event: { title: string }) => {
    browserSessionStore.updateSession(browserId, { title: event.title });
  };

  const onFavicon = (event: { favicons: string[] }) => {
    browserSessionStore.updateSession(browserId, { faviconUrl: event.favicons[0] });
  };

  webview.addEventListener('dom-ready', onDomReady);
  webview.addEventListener('did-start-loading', onStartLoading);
  webview.addEventListener('did-stop-loading', onStopLoading);
  webview.addEventListener('did-navigate', onNavigate);
  webview.addEventListener('did-navigate-in-page', onNavigate);
  webview.addEventListener('did-fail-load', onFailLoad);
  webview.addEventListener('page-title-updated', onTitle);
  webview.addEventListener('page-favicon-updated', onFavicon);

  return () => {
    for (const timer of historySyncTimers) clearTimeout(timer);
    historySyncTimers.clear();
    webview.removeEventListener('dom-ready', onDomReady);
    webview.removeEventListener('did-start-loading', onStartLoading);
    webview.removeEventListener('did-stop-loading', onStopLoading);
    webview.removeEventListener('did-navigate', onNavigate);
    webview.removeEventListener('did-navigate-in-page', onNavigate);
    webview.removeEventListener('did-fail-load', onFailLoad);
    webview.removeEventListener('page-title-updated', onTitle);
    webview.removeEventListener('page-favicon-updated', onFavicon);
  };
}
