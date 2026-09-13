import { beforeEach, describe, expect, it, vi } from 'vitest';

Object.defineProperty(process, 'getCreationTime', {
  configurable: true,
  value: () => Date.now(),
});

type IpcHandler = (_event: unknown, action: unknown) => Promise<void>;

const mocks = vi.hoisted(() => ({
  appExit: vi.fn(),
  appRelaunch: vi.fn(),
  appScopeDispose: vi.fn(),
  bootWindow: vi.fn(),
  destroyMainWindow: vi.fn(),
  destroyTray: vi.fn(),
  disableMainWindowCreation: vi.fn(),
  finishBoot: vi.fn(),
  handle: vi.fn(),
  ipcHandler: undefined as IpcHandler | undefined,
  observePreviousBoot: vi.fn(),
  recordBootFailure: vi.fn(),
  reportBootSuccessSignal: vi.fn(),
  runBootPreflight: vi.fn(),
  startBootWatchdog: vi.fn(),
  watchdogDisarm: vi.fn(),
  writeBootingMarker: vi.fn(),
}));

vi.mock('electron', () => ({
  app: {
    exit: mocks.appExit,
    relaunch: mocks.appRelaunch,
  },
  ipcMain: {
    handle: mocks.handle,
    on: vi.fn(),
  },
}));
vi.mock('@main/lib/logger', () => ({
  log: { error: vi.fn(), info: vi.fn(), warn: vi.fn() },
}));
vi.mock('./boot/preflight', () => ({ runBootPreflight: mocks.runBootPreflight }));
vi.mock('./core/boot-guard', () => ({
  markBootSuccessful: vi.fn(),
  observePreviousBoot: mocks.observePreviousBoot,
  recordBootFailure: mocks.recordBootFailure,
  writeBootingMarker: mocks.writeBootingMarker,
}));
vi.mock('./core/boot-report', () => ({
  notifyBootSettledForReport: vi.fn(),
  recordUsableWorkspace: vi.fn(),
}));
vi.mock('./core/boot-status', () => ({
  bootSuccessSignalsSeen: vi.fn(() => ({ backend: false, windowLoaded: false })),
  onBootSettled: vi.fn(),
  reportBootSuccessSignal: mocks.reportBootSuccessSignal,
}));
vi.mock('./core/boot-watchdog', () => ({
  shouldRecoverFromBootWatchdog: vi.fn(() => false),
  startBootWatchdog: mocks.startBootWatchdog,
}));
vi.mock('./core/config', () => ({
  loadAppConfig: vi.fn(() => ({})),
  setAppConfig: vi.fn(),
}));
vi.mock('./core/phase', () => ({
  step: vi.fn((_name: string, operation: () => unknown) => operation()),
}));
vi.mock('./boot/phases/window', () => ({ bootWindow: mocks.bootWindow }));
vi.mock('./boot', () => ({ finishBoot: mocks.finishBoot }));
vi.mock('./core/app-scope', () => ({
  appScope: { dispose: mocks.appScopeDispose },
}));
vi.mock('@main/host/window', () => ({
  disableMainWindowCreation: mocks.disableMainWindowCreation,
  getMainWindow: vi.fn(() => ({
    destroy: mocks.destroyMainWindow,
    isDestroyed: vi.fn(() => false),
  })),
}));
vi.mock('@main/host/tray', () => ({ destroyTray: mocks.destroyTray }));

import { main } from './index';

describe('bootstrap recovery escape', () => {
  beforeEach(() => {
    for (const mock of Object.values(mocks)) {
      if (typeof mock === 'function' && 'mockReset' in mock) mock.mockReset();
    }
    mocks.ipcHandler = undefined;
    mocks.handle.mockImplementation((channel: string, handler: IpcHandler) => {
      if (channel === 'emdash:boot-escape') mocks.ipcHandler = handler;
    });
    mocks.observePreviousBoot.mockReturnValue({ failures: 0 });
    mocks.startBootWatchdog.mockReturnValue({ disarm: mocks.watchdogDisarm });
    mocks.finishBoot.mockImplementation((_config: unknown, signal: AbortSignal) => {
      return new Promise<void>((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(signal.reason), { once: true });
      });
    });
  });

  it('aborts in-flight backend work and uses the normal failure cleanup', async () => {
    const boot = main().then(
      () => undefined,
      (error: unknown) => error
    );
    await vi.waitFor(() => expect(mocks.ipcHandler).toBeTypeOf('function'));

    await mocks.ipcHandler!({}, 'open-recovery');
    await expect(boot).resolves.toMatchObject({
      message: 'Recovery was requested from the boot escape hatch',
    });

    const signal = mocks.finishBoot.mock.calls[0]?.[1] as AbortSignal;
    expect(signal.aborted).toBe(true);
    expect(mocks.recordBootFailure).toHaveBeenCalledOnce();
    expect(mocks.appScopeDispose).toHaveBeenCalledOnce();
    expect(mocks.disableMainWindowCreation).toHaveBeenCalledOnce();
    expect(mocks.destroyMainWindow).toHaveBeenCalledOnce();
    expect(mocks.destroyTray).toHaveBeenCalledOnce();
  });
});
