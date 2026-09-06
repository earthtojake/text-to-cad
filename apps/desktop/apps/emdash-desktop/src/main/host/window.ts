import { join } from 'node:path';
import { app, BrowserWindow, nativeTheme } from 'electron';
import devIcon from '@/assets/images/hardcore/hardcore-dev.png?asset';
import { desktopHostEvents } from '@core/features/workbench/node';
import { PRODUCT_NAME } from '@core/primitives/app-identity/api/app-identity';
import type { Theme } from '@core/primitives/app-settings/api';
import { recordWindowVisible } from '@main/bootstrap/core/boot-report';
import { reportBootSuccessSignal } from '@main/bootstrap/core/boot-status';
import {
  isShutdownInProgress,
  shouldAllowWindowClose,
  watchWindow,
} from '@main/bootstrap/shutdown';
import { browserWebContentsRegistry } from '@main/host/browser/browser-webcontents-registry';
import {
  hardenBrowserWebviewPreferences,
  stripBrowserWebviewParams,
  validateBrowserWebviewAttach,
} from '@main/host/browser/webview-security';
import { registerExternalLinkHandlers } from '@main/host/externalLinks';
import { createMainWindowLifecycle } from '@main/host/main-window-lifecycle';
import { log } from '@main/lib/logger';
import { telemetryService } from '@main/lib/telemetry';
import { APP_ORIGIN } from './protocol';
import { createRendererFailureGuard } from './renderer-failure-guard';

let mainWindow: BrowserWindow | null = null;
const mainWindowLifecycle = createMainWindowLifecycle();

export type MainWindowOptions = {
  onRendererFailure?: (error: Error) => void;
  onRendererLoaded?: () => void;
};

export function applyNativeTheme(theme: Theme): void {
  if (process.platform !== 'win32') return;
  nativeTheme.themeSource = theme === 'emdark' ? 'dark' : theme === 'emlight' ? 'light' : 'system';
}

export function createMainWindow(options: MainWindowOptions = {}): BrowserWindow {
  mainWindow = new BrowserWindow({
    width: 1400,
    height: 900,
    minWidth: 700,
    minHeight: 500,
    title: PRODUCT_NAME,
    // sRGB approximation of the theme --background tokens, so the window that
    // appears before the splash paints is not a white flash. System-theme
    // heuristic: the DB-backed app theme is not readable this early; the
    // splash corrects to the persisted theme as soon as index.html parses.
    backgroundColor: nativeTheme.shouldUseDarkColors ? '#111111' : '#fcfcfc',
    // In production, electron-builder injects the icon from the app bundle.
    ...(import.meta.env.DEV && { icon: devIcon }),
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      // Required for ESM preload scripts (.mjs)
      sandbox: false,
      // Allow using <webview> in renderer for in‑app browser pane.
      // The webview runs in a separate process; nodeIntegration remains disabled.
      webviewTag: true,
      // app.getAppPath() is stable regardless of which output chunk this module
      // lands in after code splitting. Preload is built to out/preload/index.mjs.
      preload: join(app.getAppPath(), 'out', 'preload', 'index.mjs'),
    },
    ...(process.platform === 'darwin'
      ? {
          titleBarStyle: 'hiddenInset',
          trafficLightPosition: { x: 10, y: 10 },
          acceptFirstMouse: true,
        }
      : {}),
    // Linux: go fully frameless and draw our own window controls in the
    // renderer (see WindowControls). Electron's native titleBarOverlay is
    // experimental/inconsistent across desktop environments, so we avoid it —
    // this mirrors how VSCode handles its custom title bar on Linux.
    ...(process.platform === 'linux' ? { frame: false } : {}),
    show: false,
  });
  watchWindow(mainWindow);
  const rendererFailureGuard = createRendererFailureGuard((error) => {
    if (isShutdownInProgress()) return;
    log.error('Renderer startup failed', { error });
    options.onRendererFailure?.(error);
  });
  mainWindow.webContents.on(
    'did-fail-load',
    (_event, errorCode, errorDescription, validatedURL, isMainFrame) => {
      rendererFailureGuard.didFailLoad({
        errorCode,
        errorDescription,
        validatedURL,
        isMainFrame,
      });
    }
  );
  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    rendererFailureGuard.renderProcessGone(details);
  });
  mainWindow.webContents.once('did-finish-load', () => {
    log.info('boot-timeline', {
      mark: 'window-did-finish-load',
      sinceProcessStartMs: Date.now() - (process.getCreationTime() ?? Date.now()),
    });
    // One of the two boot success signals; the crash-loop marker clears only
    // when the backend chain has also finished (see boot-status).
    reportBootSuccessSignal('window-load');
    options.onRendererLoaded?.();
  });

  if (process.platform !== 'darwin') {
    mainWindow.setMenuBarVisibility(false);
  }

  const rendererLoad = import.meta.env.DEV
    ? mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL!)
    : mainWindow.loadURL(`${APP_ORIGIN}/index.html`);
  void rendererLoad.catch((error: unknown) => rendererFailureGuard.loadPromiseRejected(error));

  // Route external links to the user’s default browser
  registerExternalLinkHandlers(mainWindow, import.meta.env.DEV);
  registerBrowserWebviewHandlers(mainWindow);

  // Window-first: show immediately with the theme-matching background instead
  // of waiting for ready-to-show. For a module-script page, ready-to-show only
  // fires once the whole renderer bundle has evaluated (DOMContentLoaded waits
  // on deferred scripts), which would hide the window — and the splash — for
  // the full renderer load. Electron's own guidance for complex apps is to
  // show immediately with a backgroundColor; the static splash in index.html
  // paints on top as soon as the HTML parses.
  mainWindow.show();
  const windowVisibleMs = Date.now() - (process.getCreationTime() ?? Date.now());
  log.info('boot-timeline', { mark: 'window-visible', sinceProcessStartMs: windowVisibleMs });
  recordWindowVisible(windowVisibleMs);

  // Diagnostic only (the window is already visible): marks when the renderer
  // produced its first full frame.
  mainWindow.once('ready-to-show', () => {
    log.info('boot-timeline', {
      mark: 'window-ready-to-show',
      sinceProcessStartMs: Date.now() - (process.getCreationTime() ?? Date.now()),
    });
  });

  // Track window focus for telemetry
  mainWindow.on('focus', () => {
    telemetryService.capture('app_window_focused');
    if (typeof mainWindow?.setWindowButtonVisibility === 'function') {
      mainWindow.setWindowButtonVisibility(true);
    }
    void telemetryService.checkAndReportDailyActiveUser();
  });

  mainWindow.on('blur', () => {
    telemetryService.capture('app_window_unfocused');
  });

  mainWindow.on('close', (event) => {
    if (shouldAllowWindowClose()) return;
    event.preventDefault();
    if (isShutdownInProgress()) return;
    mainWindow?.hide();
  });

  // Keep the renderer's custom window controls (Linux) in sync with the
  // actual maximize state so the maximize/restore icon stays correct.
  mainWindow.on('maximize', () => {
    desktopHostEvents.emit(undefined, { type: 'window-maximize-changed', maximized: true });
  });
  mainWindow.on('unmaximize', () => {
    desktopHostEvents.emit(undefined, { type: 'window-maximize-changed', maximized: false });
  });

  // Cleanup reference on close
  mainWindow.on('closed', () => {
    mainWindow = null;
  });

  return mainWindow;
}

export function getMainWindow(): BrowserWindow | null {
  return mainWindow;
}

export function disableMainWindowCreation(): void {
  mainWindowLifecycle.disableCreation();
}

export function showMainWindow(): BrowserWindow | null {
  if (!mainWindowLifecycle.canCreate() && (!mainWindow || mainWindow.isDestroyed())) return null;
  const win = mainWindow && !mainWindow.isDestroyed() ? mainWindow : createMainWindow();
  if (win.isMinimized()) win.restore();
  win.show();
  if (process.platform === 'darwin') {
    app.focus({ steal: true });
  } else {
    app.focus();
  }
  win.focus();
  return win;
}

export function isAppFocused(): boolean {
  const windows = BrowserWindow.getAllWindows();
  return windows.some((window) => !window.isDestroyed() && window.isFocused());
}

export function focusAppFromNotification(): BrowserWindow | null {
  const win = getMainWindow();
  if (!win || win.isDestroyed()) return null;
  return showMainWindow();
}

function registerBrowserWebviewHandlers(win: BrowserWindow): void {
  win.webContents.on('will-attach-webview', (event, webPreferences, params) => {
    const validation = validateBrowserWebviewAttach(
      params,
      browserWebContentsRegistry.registeredPartitions
    );
    if (!validation.ok) {
      event.preventDefault();
      log.warn('Denied browser webview attachment', { reason: validation.reason });
      return;
    }

    hardenBrowserWebviewPreferences(webPreferences);
    stripBrowserWebviewParams(params);
  });

  win.webContents.on('did-attach-webview', (_event, webContents) => {
    if (!browserWebContentsRegistry.handleWebviewAttached(webContents)) {
      log.warn('Closed webview without a registered browser session');
    }
  });
}
