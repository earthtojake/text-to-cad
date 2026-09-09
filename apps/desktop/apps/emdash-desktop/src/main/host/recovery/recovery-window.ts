import { join } from 'node:path';
import { app, BrowserWindow, shell } from 'electron';
import { clearBootFailureMarker } from '@main/bootstrap/core/boot-guard';
import { getLogFilePath } from '@main/host/file-logger';
import { log } from '@main/lib/logger';
import { injectBootstrap, type RecoveryState } from './recovery-bootstrap';
import recoveryHtmlTemplate from './recovery.html?raw';

export type RecoveryWindowOptions = {
  errorMessage: string;
};

// Minimal structural interface — avoids a static import of the updater module
// graph. The real updateService satisfies this interface at runtime.
interface RecoveryUpdateService {
  initialize(): Promise<void>;
  checkForUpdates(): Promise<unknown>;
  downloadUpdate(): Promise<void>;
  quitAndInstall(): void;
  getState(): {
    status: string;
    availableVersion?: string;
    downloadProgress?: { percent: number };
    error?: string;
  };
  readonly isActive: boolean;
}

// Minimal interface for the update event stream — avoids importing @emdash/wire.
interface RecoveryUpdateEvents {
  resolve(key: undefined): { subscribe(cb: () => void): () => void };
}

let recoveryWindow: BrowserWindow | undefined;

export async function showRecoveryWindow(options: RecoveryWindowOptions): Promise<BrowserWindow> {
  if (recoveryWindow && !recoveryWindow.isDestroyed()) {
    recoveryWindow.show();
    recoveryWindow.focus();
    return recoveryWindow;
  }

  // Load the updater dynamically. If its module graph fails to evaluate (e.g.
  // native add-on missing or asar extraction failure), the window still opens.
  let updateSvc: RecoveryUpdateService | null = null;
  let updateEventSource: RecoveryUpdateEvents | null = null;

  try {
    const [updaterModule, eventsModule] = await Promise.all([
      import('@main/host/updates/update-service'),
      import('@core/features/updates/node'),
    ]);
    // initialize() is idempotent, so recovery can safely call it even if the
    // normal updater phase completed before a later boot phase failed.
    await updaterModule.updateService.initialize();
    updateSvc = updaterModule.updateService;
    // Cast to the minimal interface — EventStreamHost satisfies it structurally.
    updateEventSource = eventsModule.updateEvents as unknown as RecoveryUpdateEvents;
  } catch (err) {
    log.warn('Update service unavailable in recovery mode', { error: err });
  }

  function buildState(): RecoveryState {
    const upd = updateSvc?.getState();
    return {
      errorMessage: options.errorMessage,
      version: app.getVersion(),
      updaterActive: updateSvc?.isActive ?? false,
      updateStatus: upd?.status ?? 'idle',
      availableVersion: upd?.availableVersion,
      downloadProgress: upd?.downloadProgress?.percent,
      error: upd?.error,
    };
  }

  // Inject the initial state synchronously so the page renders immediately
  // without any async round-trip.
  const html = injectBootstrap(recoveryHtmlTemplate, buildState());

  const window = new BrowserWindow({
    width: 560,
    height: 480,
    minWidth: 440,
    minHeight: 380,
    title: 'Hardcore Recovery',
    show: false,
    autoHideMenuBar: true,
    webPreferences: {
      nodeIntegration: false,
      contextIsolation: true,
      // sandbox: true removes the need for a preload file entirely. The page
      // communicates via hardcore-recovery:// navigation URLs instead of IPC.
      sandbox: true,
    },
  });
  recoveryWindow = window;

  function pushState(): void {
    if (window.isDestroyed()) return;
    const json = JSON.stringify(buildState());
    // An event can arrive before the data URL defines renderState. That is
    // harmless: the initial state is embedded in the HTML, and later events
    // retry this push.
    window.webContents.executeJavaScript(`window.renderState(${json})`).catch((err) => {
      log.warn('Recovery: failed to push state update', { error: err });
    });
  }

  window.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));

  // Actions are encoded as hardcore-recovery://<action> navigation URLs set by
  // the page. The scheme is intentionally unregistered: will-navigate fires
  // before Chromium resolves it, and preventDefault() keeps the page in place.
  window.webContents.on('will-navigate', (event, url) => {
    event.preventDefault();
    const prefix = 'hardcore-recovery://';
    if (!url.startsWith(prefix)) return;
    const action = url.slice(prefix.length);
    void dispatchAction(action);
  });

  async function dispatchAction(action: string): Promise<void> {
    switch (action) {
      case 'check':
        try {
          await updateSvc?.checkForUpdates();
        } catch (err) {
          log.warn('Recovery: update check failed', { error: err });
        }
        pushState();
        break;

      case 'download':
        try {
          await updateSvc?.downloadUpdate();
        } catch (err) {
          log.warn('Recovery: download failed', { error: err });
        }
        pushState();
        break;

      case 'install':
        clearBootFailureMarker();
        try {
          updateSvc?.quitAndInstall();
        } catch (err) {
          log.warn('Recovery: install failed', { error: err });
          pushState();
        }
        break;

      case 'restart':
        clearBootFailureMarker();
        app.relaunch();
        app.exit(0);
        break;

      case 'open-logs': {
        const logFilePath = getLogFilePath();
        if (logFilePath) {
          shell.showItemInFolder(logFilePath);
        } else {
          await shell.openPath(join(app.getPath('userData'), 'logs'));
        }
        break;
      }

      case 'quit':
        app.quit();
        break;

      default:
        log.warn('Recovery: unknown action', { action });
    }
  }

  // Subscribe to update events and push state on each change.
  let unsubscribeUpdates: (() => void) | undefined;
  if (updateEventSource) {
    unsubscribeUpdates = updateEventSource.resolve(undefined).subscribe(pushState);
  }

  window.on('closed', () => {
    unsubscribeUpdates?.();
    if (recoveryWindow === window) recoveryWindow = undefined;
    app.quit();
  });
  window.once('ready-to-show', () => window.show());

  // Load as a data URL — no file on disk to mis-resolve. The full HTML is
  // already inlined as a string by the ?raw import at build time.
  await window.loadURL('data:text/html;charset=utf-8,' + encodeURIComponent(html));
  return window;
}
