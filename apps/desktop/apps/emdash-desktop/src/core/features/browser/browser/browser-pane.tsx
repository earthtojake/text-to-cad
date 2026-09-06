import { Button } from '@emdash/ui/react/primitives';
import { observer } from 'mobx-react-lite';
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from 'react';
import { browserControlsRegistry } from '@core/features/browser/api/browser/browser-controls-registry';
import { browserSessionStore } from '@core/features/browser/api/browser/browser-session-store';
import { getBrowserClient } from '@core/features/browser/api/browser/client';
import {
  cycleNextTabCommand,
  cyclePreviousTabCommand,
} from '@core/features/workbench/contributions/commands';
import { normalizeBrowserUrl, normalizeBrowserZoomFactor } from '@core/primitives/browser/api';
import { getHostClient } from '@core/primitives/desktop-host/browser/host-client';
import { usePaneContext } from '@core/primitives/workbench-shell/browser/tabs/pane-context';
import {
  browserLoadErrorCode,
  describeBrowserLoadError,
  type BrowserLoadErrorPresentation,
} from './browser-load-error';
import { decideBrowserReload } from './browser-navigation-controls';
import { BrowserToolbar } from './browser-toolbar';
import { canOpenBrowserUrlExternally, openBrowserUrlExternally } from './browser-toolbar-actions';
import { bindBrowserWebviewEvents } from './browser-webview-events';
import {
  createBrowserWebviewAdapter,
  type BrowserWebviewAdapter,
  type BrowserWebviewElement,
} from './browser-webview-types';

const WEBVIEW_ALLOW_POPUPS_ATTRIBUTE = 'true' as unknown as boolean;
const VISIBLE_WEBVIEW_STYLE = {
  display: 'flex',
  visibility: 'visible',
  width: '100%',
  height: '100%',
} satisfies CSSProperties;
const HIDDEN_WEBVIEW_STYLE = {
  display: 'none',
  visibility: 'hidden',
  width: 0,
  height: 0,
} satisfies CSSProperties;

export const BrowserPane = observer(function BrowserPane({
  browserId,
  visible,
  showToolbar = true,
  onDomReady,
}: {
  browserId: string;
  visible: boolean;
  showToolbar?: boolean;
  onDomReady?: () => void;
}) {
  const session = browserSessionStore.getSession(browserId);
  const { pane, scopeInstance } = usePaneContext();
  const effectiveVisible = visible && pane.isVisible;
  const webviewRef = useRef<BrowserWebviewElement | null>(null);
  const focusUrlRef = useRef<() => void>(() => {});
  const [adapter, setAdapter] = useState<BrowserWebviewAdapter | null>(null);
  const [webviewElement, setWebviewElement] = useState<BrowserWebviewElement | null>(null);
  const [webviewMount, setWebviewMount] = useState<{
    browserId: string;
    partition: string;
    src: string;
    revision: number;
  } | null>(null);
  const [isRegistered, setIsRegistered] = useState(false);
  const sessionBrowserId = session?.browserId;
  const sessionPartition = session?.partition;
  const sessionCurrentUrl = session?.currentUrl;
  const showStartPage = session?.currentUrl === 'about:blank' && !session.isLoading;
  const loadError = session && !session.isLoading ? session.loadError : undefined;
  const loadErrorUrl = loadError ? (loadError.url ?? session?.currentUrl ?? '') : '';
  const loadErrorPresentation = useMemo<BrowserLoadErrorPresentation | undefined>(
    () => (loadError ? describeBrowserLoadError(loadError, loadErrorUrl) : undefined),
    [loadError, loadErrorUrl]
  );
  const canOpenLoadErrorExternal = useMemo(
    () => (loadError ? canOpenBrowserUrlExternally(loadErrorUrl) : false),
    [loadError, loadErrorUrl]
  );

  useEffect(() => {
    if (!sessionBrowserId || !sessionPartition || !session) {
      setWebviewMount(null);
      return;
    }
    setWebviewMount((current) => {
      if (current?.browserId === sessionBrowserId && current.partition === sessionPartition) {
        return current;
      }
      return {
        browserId: sessionBrowserId,
        partition: sessionPartition,
        src: session.currentUrl,
        revision: 0,
      };
    });
  }, [session, sessionBrowserId, sessionPartition]);

  useEffect(() => {
    if (!sessionBrowserId || !sessionPartition) return;
    let disposed = false;
    setIsRegistered(false);
    void getBrowserClient()
      .then((client) =>
        client.registerSession({
          browserId: sessionBrowserId,
          partition: sessionPartition,
        })
      )
      .then((result) => {
        if (!disposed) setIsRegistered(result.success);
      });
    return () => {
      disposed = true;
      setIsRegistered(false);
    };
  }, [sessionBrowserId, sessionPartition]);

  useEffect(() => {
    return () => {
      void getBrowserClient().then((client) => client.setActiveBrowser({ browserId: null }));
    };
  }, []);

  useEffect(() => {
    return () => {
      if (!sessionBrowserId) return;
      void getBrowserClient().then((client) =>
        client.releaseWebContents({ browserId: sessionBrowserId })
      );
    };
  }, [sessionBrowserId]);

  useEffect(() => {
    if (pane.isVisible || !sessionBrowserId) return;
    setWebviewMount((current) => {
      if (!current || sessionCurrentUrl === undefined || current.src === sessionCurrentUrl) {
        return current;
      }
      return { ...current, src: sessionCurrentUrl };
    });
    void getBrowserClient().then((client) =>
      client.releaseWebContents({ browserId: sessionBrowserId })
    );
  }, [pane.isVisible, sessionBrowserId, sessionCurrentUrl]);

  useEffect(() => {
    if (!effectiveVisible || !sessionBrowserId || adapter === null) return;
    void getBrowserClient().then((client) =>
      client.setActiveBrowser({ browserId: sessionBrowserId })
    );
  }, [adapter, effectiveVisible, sessionBrowserId]);

  useEffect(() => {
    if (!effectiveVisible || !sessionBrowserId) return;
    let disposed = false;
    let unsubscribe: (() => void) | undefined;
    void getHostClient().then(async (client) => {
      const nextUnsubscribe = await client.events.subscribe(undefined, {
        onEvent: (event) => {
          if (
            event.type !== 'tab-navigation-shortcut' ||
            event.source.browserId !== sessionBrowserId
          ) {
            return;
          }
          const command =
            event.direction === 'next' ? cycleNextTabCommand : cyclePreviousTabCommand;
          void scopeInstance?.getCommand(command)?.execute(undefined, 'keybinding');
        },
        onGap: () => {},
      });
      if (disposed) nextUnsubscribe();
      else unsubscribe = nextUnsubscribe;
    });
    return () => {
      disposed = true;
      unsubscribe?.();
    };
  }, [effectiveVisible, sessionBrowserId, scopeInstance]);

  const webviewProps = useMemo(() => {
    if (!webviewMount) return null;
    return {
      src: webviewMount.src,
      partition: webviewMount.partition,
      allowpopups: WEBVIEW_ALLOW_POPUPS_ATTRIBUTE,
      'data-browser-id': webviewMount.browserId,
    };
  }, [webviewMount]);

  const loadUrl = useCallback(
    (url: string) => {
      if (!sessionBrowserId) return;
      browserSessionStore.updateSession(sessionBrowserId, {
        currentUrl: url,
        faviconUrl: null,
        isLoading: true,
        loadError: null,
      });
      if (adapter) {
        void adapter.loadUrl(url);
        return;
      }
      setWebviewMount((current) => {
        if (!current) return current;
        return {
          ...current,
          src: url,
          revision: current.revision + 1,
        };
      });
    },
    [adapter, sessionBrowserId]
  );

  const navigateTo = useCallback(
    (url: string): boolean => {
      const normalized = normalizeBrowserUrl(url);
      if (!normalized.ok) return false;
      loadUrl(normalized.url);
      return true;
    },
    [loadUrl]
  );

  const goBack = useCallback(() => {
    if (!adapter?.canGoBack()) return;
    adapter.goBack();
  }, [adapter]);

  const goForward = useCallback(() => {
    if (!adapter?.canGoForward()) return;
    adapter.goForward();
  }, [adapter]);

  const reload = useCallback(() => {
    if (!session) return;
    const decision = decideBrowserReload({
      currentUrl: session.currentUrl,
      isLoading: session.isLoading,
      hasAdapter: adapter !== null,
    });
    if (decision.kind === 'reload-adapter') adapter?.reload();
    if (decision.kind === 'stop-adapter') adapter?.stop();
    if (decision.kind === 'retry-url') loadUrl(decision.url);
  }, [adapter, loadUrl, session]);

  const forceReload = useCallback(() => {
    if (adapter) {
      adapter.reloadIgnoringCache();
      return;
    }
    reload();
  }, [adapter, reload]);

  const setZoomFactor = useCallback(
    (factor: number) => {
      if (!sessionBrowserId) return;
      const zoomFactor = normalizeBrowserZoomFactor(factor);
      browserSessionStore.updateSession(sessionBrowserId, {
        zoomFactor,
      });
      adapter?.setZoomFactor(zoomFactor);
    },
    [adapter, sessionBrowserId]
  );

  // Must stay referentially stable: React re-invokes inline ref callbacks with
  // null + node on every render, which would wipe the adapter until the next
  // dom-ready and break everything adapter-backed (zoom, stop, force reload).
  const attachWebview = useCallback((node: Element | null) => {
    const next = node as BrowserWebviewElement | null;
    if (webviewRef.current === next) return;
    webviewRef.current = next;
    setWebviewElement(next);
    setAdapter(null);
  }, []);

  useEffect(() => {
    if (!sessionBrowserId || !webviewElement) return;
    return bindBrowserWebviewEvents(sessionBrowserId, webviewElement, {
      onDomReady: () => {
        if (webviewRef.current !== webviewElement) return;
        // Browsers can share profile partitions, so the main process cannot infer
        // which browser a webview belongs to; bind it explicitly.
        void getBrowserClient().then((client) =>
          client.bindWebContents({
            browserId: sessionBrowserId,
            webContentsId: webviewElement.getWebContentsId(),
          })
        );
        setAdapter(createBrowserWebviewAdapter(webviewElement));
        onDomReady?.();
      },
    });
  }, [onDomReady, sessionBrowserId, webviewElement]);

  useEffect(() => {
    if (!sessionBrowserId) return;
    return browserControlsRegistry.register(sessionBrowserId, {
      adapter,
      focusUrl: () => focusUrlRef.current(),
    });
  }, [adapter, sessionBrowserId]);

  if (!session) {
    return (
      <div className="flex h-full min-h-0 items-center justify-center bg-background text-sm text-foreground-muted">
        Browser session unavailable
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col bg-background">
      {showToolbar ? (
        <BrowserToolbar
          session={session}
          adapter={adapter}
          autoFocusUrl={showStartPage}
          onNavigate={navigateTo}
          onGoBack={goBack}
          onGoForward={goForward}
          onReload={reload}
          onForceReload={forceReload}
          onSetZoomFactor={setZoomFactor}
          onFocusUrl={(focus) => {
            focusUrlRef.current = focus;
          }}
        />
      ) : null}
      <div className="emlight min-h-0 flex-1 bg-background">
        {loadError && loadErrorPresentation ? (
          <BrowserLoadErrorView
            url={loadErrorUrl}
            presentation={loadErrorPresentation}
            code={browserLoadErrorCode(loadError)}
            canOpenExternal={canOpenLoadErrorExternal}
            onReload={reload}
            onOpenExternal={() => openBrowserUrlExternally(loadErrorUrl)}
          />
        ) : showStartPage ? (
          <div className="flex h-full items-center justify-center text-sm text-foreground-muted">
            Enter a URL to open a reference page.
          </div>
        ) : webviewProps && isRegistered && pane.isVisible ? (
          <webview
            key={`${webviewMount?.browserId ?? 'browser'}:${webviewMount?.partition ?? 'partition'}:${webviewMount?.revision ?? 0}`}
            ref={attachWebview}
            {...webviewProps}
            hidden={!visible}
            aria-hidden={!visible}
            style={visible ? VISIBLE_WEBVIEW_STYLE : HIDDEN_WEBVIEW_STYLE}
            className="h-full w-full bg-background"
          />
        ) : effectiveVisible ? (
          <div className="flex h-full items-center justify-center text-sm text-foreground-muted">
            Preparing browser session
          </div>
        ) : null}
      </div>
    </div>
  );
});

function BrowserLoadErrorView({
  presentation,
  code,
  url,
  canOpenExternal,
  onReload,
  onOpenExternal,
}: {
  presentation: BrowserLoadErrorPresentation;
  code: string | null;
  url: string;
  canOpenExternal: boolean;
  onReload: () => void;
  onOpenExternal: () => void;
}) {
  return (
    <div className="flex h-full min-h-0 items-center justify-center overflow-auto p-8">
      <div className="flex max-w-sm flex-col items-center gap-2 text-center">
        <h1 className="text-base font-medium text-foreground">{presentation.heading}</h1>
        <p className="text-sm text-foreground-muted" title={url}>
          {presentation.detail}
          {code && <span className="text-foreground-tertiary-muted"> ({code})</span>}
        </p>
        <div className="mt-2 flex flex-wrap items-center justify-center gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={onReload}>
            Reload
          </Button>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            disabled={!canOpenExternal}
            onClick={onOpenExternal}
          >
            Open externally
          </Button>
        </div>
      </div>
    </div>
  );
}
