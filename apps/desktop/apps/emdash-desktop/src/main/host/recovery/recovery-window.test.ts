import { expect, it, vi } from 'vitest';

type NavigationListener = (event: { preventDefault(): void }, url: string) => void | Promise<void>;

const mocks = vi.hoisted(() => ({
  checkForUpdates: vi.fn(async () => null),
  clearBootFailureMarker: vi.fn(),
  downloadUpdate: vi.fn(async () => {}),
  executeJavaScript: vi.fn(async () => undefined),
  exit: vi.fn(),
  initialize: vi.fn(async () => {}),
  loadURL: vi.fn(async () => {}),
  navigationListener: undefined as NavigationListener | undefined,
  openPath: vi.fn(async () => ''),
  quit: vi.fn(),
  quitAndInstall: vi.fn(),
  relaunch: vi.fn(),
  setWindowOpenHandler: vi.fn(),
  showItemInFolder: vi.fn(),
  subscribe: vi.fn(() => vi.fn()),
}));

vi.mock('electron', () => {
  class BrowserWindow {
    readonly webContents = {
      executeJavaScript: mocks.executeJavaScript,
      on: (event: string, listener: NavigationListener) => {
        if (event === 'will-navigate') mocks.navigationListener = listener;
      },
      setWindowOpenHandler: mocks.setWindowOpenHandler,
    };

    isDestroyed(): boolean {
      return false;
    }

    show(): void {}

    focus(): void {}

    on(): void {}

    once(): void {}

    loadURL = mocks.loadURL;
  }

  return {
    app: {
      exit: mocks.exit,
      getPath: () => '/tmp/emdash-recovery-test',
      getVersion: () => '1.2.3',
      quit: mocks.quit,
      relaunch: mocks.relaunch,
    },
    BrowserWindow,
    shell: {
      openPath: mocks.openPath,
      showItemInFolder: mocks.showItemInFolder,
    },
  };
});
vi.mock('@core/features/updates/node', () => ({
  updateEvents: {
    resolve: () => ({ subscribe: mocks.subscribe }),
  },
}));
vi.mock('@main/bootstrap/core/boot-guard', () => ({
  clearBootFailureMarker: mocks.clearBootFailureMarker,
}));
vi.mock('@main/host/file-logger', () => ({
  getLogFilePath: () => '/tmp/emdash.log',
}));
vi.mock('@main/host/updates/update-service', () => ({
  updateService: {
    checkForUpdates: mocks.checkForUpdates,
    downloadUpdate: mocks.downloadUpdate,
    getState: () => ({ status: 'idle' }),
    initialize: mocks.initialize,
    isActive: true,
    quitAndInstall: mocks.quitAndInstall,
  },
}));
vi.mock('@main/lib/logger', () => ({
  log: { warn: vi.fn() },
}));

import { showRecoveryWindow } from './recovery-window';

it('dispatches every recovery navigation action in the main process', async () => {
  await showRecoveryWindow({ errorMessage: 'forced failure' });

  expect(mocks.navigationListener).toBeDefined();
  const navigate = async (action: string): Promise<void> => {
    const preventDefault = vi.fn();
    await mocks.navigationListener?.({ preventDefault }, `hardcore-recovery://${action}`);
    expect(preventDefault).toHaveBeenCalledOnce();
  };

  await navigate('check');
  await vi.waitFor(() => expect(mocks.checkForUpdates).toHaveBeenCalledOnce());

  await navigate('download');
  await vi.waitFor(() => expect(mocks.downloadUpdate).toHaveBeenCalledOnce());

  await navigate('install');
  await vi.waitFor(() => expect(mocks.quitAndInstall).toHaveBeenCalledOnce());

  await navigate('open-logs');
  await vi.waitFor(() => expect(mocks.showItemInFolder).toHaveBeenCalledWith('/tmp/emdash.log'));

  await navigate('restart');
  await vi.waitFor(() => expect(mocks.relaunch).toHaveBeenCalledOnce());
  expect(mocks.clearBootFailureMarker).toHaveBeenCalledTimes(2);
  expect(mocks.exit).toHaveBeenCalledWith(0);

  await navigate('quit');
  await vi.waitFor(() => expect(mocks.quit).toHaveBeenCalledOnce());
});
