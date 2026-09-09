import { randomUUID } from 'node:crypto';
import type { BrowserWindow } from 'electron';
import type {
  ActiveSessionSummary,
  DesktopHostEvent,
} from '@core/primitives/desktop-host/api/host-contract';
import { log } from '@main/lib/logger';

const CONFIRMATION_DEADLINE_MS = 60_000;
const FLUSH_DEADLINE_MS = 2_000;

export type QuitState = 'idle' | 'confirming' | 'shutting-down';
type ConfirmationSource = 'renderer' | 'timeout' | 'renderer-invalidated' | 'install';
interface ConfirmationResolution {
  confirmed: boolean;
  source: ConfirmationSource;
}

export interface ShutdownCoordinatorDependencies {
  emit(event: DesktopHostEvent): void;
  getActiveSessionSummary(): Promise<ActiveSessionSummary>;
  isInstallRequested(): boolean;
  runCleanup(): Promise<void>;
  exit(code: number): void;
}

export interface ShutdownCoordinator {
  readonly state: QuitState;
  handleQuitRequested(): Promise<void>;
  resolveQuitConfirmation(requestId: string, confirmed: boolean): void;
  ackShutdownFlush(): void;
  markShutdownReady(): void;
  watchWindow(window: BrowserWindow): void;
  isShutdownInProgress(): boolean;
}

export function createShutdownCoordinator(
  dependencies: ShutdownCoordinatorDependencies
): ShutdownCoordinator {
  let state: QuitState = 'idle';
  let activeWindow: BrowserWindow | null = null;
  let capableWebContentsId: number | null = null;
  let pendingConfirmation:
    | {
        requestId: string;
        resolve(resolution: ConfirmationResolution): void;
        timer: ReturnType<typeof setTimeout>;
      }
    | undefined;
  let pendingFlush:
    | {
        resolve(): void;
        timer: ReturnType<typeof setTimeout>;
      }
    | undefined;

  const isRendererShutdownCapable = (): boolean => {
    const window = activeWindow;
    return (
      window !== null &&
      !window.isDestroyed() &&
      window.webContents.id === capableWebContentsId &&
      !window.webContents.isDestroyed()
    );
  };

  const settleConfirmation = (confirmed: boolean, source: ConfirmationSource): void => {
    const pending = pendingConfirmation;
    if (!pending) return;
    pendingConfirmation = undefined;
    clearTimeout(pending.timer);
    pending.resolve({ confirmed, source });
  };

  const settleFlush = (): void => {
    const pending = pendingFlush;
    if (!pending) return;
    pendingFlush = undefined;
    clearTimeout(pending.timer);
    pending.resolve();
  };

  const invalidateRenderer = (webContentsId: number): void => {
    if (capableWebContentsId !== webContentsId) return;
    capableWebContentsId = null;
    settleConfirmation(false, 'renderer-invalidated');
    settleFlush();
  };

  const requestConfirmation = async (): Promise<boolean> => {
    const window = activeWindow;
    if (!window || window.isDestroyed()) return false;
    if (window.isMinimized()) window.restore();
    window.show();
    window.focus();

    const summary = await dependencies.getActiveSessionSummary();
    if (dependencies.isInstallRequested()) return true;
    if (!isRendererShutdownCapable()) return false;

    const requestId = randomUUID();
    const confirmed = new Promise<ConfirmationResolution>((resolve) => {
      const timer = setTimeout(() => {
        if (pendingConfirmation?.requestId !== requestId) return;
        log.warn('quit: renderer confirmation timed out, proceeding with shutdown');
        settleConfirmation(true, 'timeout');
      }, CONFIRMATION_DEADLINE_MS);
      pendingConfirmation = { requestId, resolve, timer };
    });

    dependencies.emit({ type: 'quit-confirmation-requested', requestId, summary });
    const result = await confirmed;
    if (!result.confirmed || result.source !== 'renderer') {
      dependencies.emit({ type: 'quit-confirmation-cancelled', requestId });
    }
    return result.confirmed;
  };

  const flushRenderer = async (): Promise<void> => {
    if (!isRendererShutdownCapable()) return;
    const flushed = new Promise<void>((resolve) => {
      const timer = setTimeout(() => {
        if (pendingFlush?.resolve !== resolve) return;
        pendingFlush = undefined;
        resolve();
      }, FLUSH_DEADLINE_MS);
      pendingFlush = { resolve, timer };
    });
    dependencies.emit({ type: 'shutdown-started' });
    await flushed;
  };

  const runShutdown = async (): Promise<void> => {
    let exited = false;
    const exit = (): void => {
      if (exited) return;
      exited = true;
      dependencies.exit(0);
    };
    const forceExit = setTimeout(() => {
      log.warn('quit: hard deadline reached, forcing exit');
      exit();
    }, 8_000);

    try {
      await flushRenderer();
      await dependencies.runCleanup();
    } catch (error) {
      log.error('quit: shutdown sequence failed', error);
    } finally {
      clearTimeout(forceExit);
      exit();
    }
  };

  return {
    get state() {
      return state;
    },
    async handleQuitRequested() {
      if (state === 'confirming' && dependencies.isInstallRequested()) {
        settleConfirmation(true, 'install');
        return;
      }
      if (state !== 'idle') return;

      if (!dependencies.isInstallRequested() && isRendererShutdownCapable()) {
        state = 'confirming';
        let confirmed = false;
        try {
          confirmed = await requestConfirmation();
        } catch (error) {
          log.error('quit: confirmation failed', error);
        }
        confirmed ||= dependencies.isInstallRequested();
        if (!confirmed) {
          state = 'idle';
          return;
        }
      }

      state = 'shutting-down';
      await runShutdown();
    },
    resolveQuitConfirmation(requestId, confirmed) {
      if (pendingConfirmation?.requestId !== requestId) return;
      settleConfirmation(confirmed, 'renderer');
    },
    ackShutdownFlush() {
      settleFlush();
    },
    markShutdownReady() {
      const window = activeWindow;
      if (!window || window.isDestroyed() || window.webContents.isDestroyed()) return;
      capableWebContentsId = window.webContents.id;
    },
    watchWindow(window) {
      activeWindow = window;
      const webContentsId = window.webContents.id;
      window.webContents.on('did-start-loading', () => invalidateRenderer(webContentsId));
      window.webContents.on('render-process-gone', () => invalidateRenderer(webContentsId));
      window.on('closed', () => {
        invalidateRenderer(webContentsId);
        if (activeWindow === window) activeWindow = null;
      });
    },
    isShutdownInProgress() {
      return state !== 'idle';
    },
  };
}
