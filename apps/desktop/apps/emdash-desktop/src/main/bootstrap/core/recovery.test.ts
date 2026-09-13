import { beforeEach, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  appOn: vi.fn(),
  initializeFileLogger: vi.fn(),
  showRecoveryWindow: vi.fn(),
  showErrorBox: vi.fn(),
}));

vi.mock('electron', () => ({
  app: {
    on: mocks.appOn,
    whenReady: vi.fn(async () => {}),
  },
  dialog: {
    showErrorBox: mocks.showErrorBox,
  },
}));
vi.mock('@main/host/file-logger', () => ({
  initializeFileLogger: mocks.initializeFileLogger,
}));
vi.mock('@main/host/recovery/recovery-window', () => ({
  showRecoveryWindow: mocks.showRecoveryWindow,
}));
vi.mock('@main/lib/logger', () => ({
  log: { error: vi.fn(), warn: vi.fn() },
}));

import { enterSafeMode } from './recovery';

beforeEach(() => {
  mocks.initializeFileLogger.mockReset();
  mocks.showRecoveryWindow.mockReset().mockResolvedValue(undefined);
  mocks.showErrorBox.mockReset();
  mocks.appOn.mockReset();
});

// NOTE: `safeModeQuitHandlerRegistered` is module-level state that persists
// across tests. The first test runs when the flag is still false; subsequent
// tests run with it already true. Tests are ordered accordingly.

it('initializes the file logger, registers the quit handler, and opens the recovery window', async () => {
  await enterSafeMode(new Error('database unavailable'));

  expect(mocks.initializeFileLogger).toHaveBeenCalledOnce();
  // Quit handler is registered once on the first call.
  expect(mocks.appOn).toHaveBeenCalledOnce();
  expect(mocks.showRecoveryWindow).toHaveBeenCalledWith({
    errorMessage: 'database unavailable',
  });
});

it('shows a native error dialog if the recovery window itself fails to open', async () => {
  mocks.showRecoveryWindow.mockRejectedValue(new Error('window creation failed'));

  await enterSafeMode(new Error('boot failed'));

  expect(mocks.showErrorBox).toHaveBeenCalledWith(
    'Something went wrong',
    expect.stringContaining('boot failed')
  );
});

it('does not re-register the quit handler on subsequent calls', async () => {
  // By the time this test runs, the first test has already set the module-level
  // safeModeQuitHandlerRegistered flag to true. Calling enterSafeMode again
  // should NOT call app.on a second time.
  await enterSafeMode(new Error('second call'));

  expect(mocks.appOn).not.toHaveBeenCalled();
});
