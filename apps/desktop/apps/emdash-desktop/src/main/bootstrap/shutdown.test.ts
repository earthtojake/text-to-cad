import type { BrowserWindow } from 'electron';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type {
  ActiveSessionSummary,
  DesktopHostEvent,
} from '@core/primitives/desktop-host/api/host-contract';
import * as databaseInstance from '@main/db/instance';
import {
  createShutdownCoordinator,
  runQuitCleanup,
  shouldAllowWindowClose,
  type ShutdownCoordinatorDependencies,
} from './shutdown';
import { configureQuitCleanupServices } from './shutdown/phases';

const mocks = vi.hoisted(() => ({
  appScopeDispose: vi.fn(),
  closeAppDb: vi.fn(),
  editorBuffersDispose: vi.fn(),
  projectsDispose: vi.fn(),
  projectsRelease: vi.fn(),
  pullRequestsDispose: vi.fn(),
  runtimesDispose: vi.fn(),
  telemetryDispose: vi.fn(),
  updateService: {
    isInstallRequested: false as boolean,
    dispose: vi.fn(),
  },
}));

vi.mock('electron', () => ({
  app: { exit: vi.fn(), on: vi.fn() },
}));
vi.mock('@core/features/workbench/node', () => ({
  desktopHostEvents: { emit: vi.fn() },
}));
vi.mock('@core/services/pull-requests/node/pull-requests-registration', () => ({
  pullRequestsRegistration: { dispose: vi.fn() },
}));
vi.mock('@main/core/acp/agent-status-bridge', () => ({
  acpAgentStatusBridge: { dispose: vi.fn() },
}));
vi.mock('@main/core/agent-status/agent-status-service', () => ({
  agentStatusService: { dispose: vi.fn() },
}));
vi.mock('@main/core/agent-status/tui-agent-status-bridge', () => ({
  tuiAgentStatusBridge: { dispose: vi.fn() },
}));
vi.spyOn(databaseInstance, 'closeAppDb').mockImplementation(mocks.closeAppDb);
vi.mock('@main/host/updates/update-service', () => ({
  updateService: mocks.updateService,
}));
vi.mock('@main/lib/logger', () => ({
  log: { error: vi.fn(), info: vi.fn(), warn: vi.fn() },
}));
vi.mock('@main/lib/telemetry', () => ({
  telemetryService: { capture: vi.fn(), dispose: mocks.telemetryDispose },
}));
vi.mock('./core/service-instances', () => ({
  disposeNotificationService: vi.fn(),
}));
vi.mock('@main/host/sessions/active-session-summary', () => ({
  getActiveSessionSummary: vi.fn(),
}));
vi.mock('./core/app-scope', () => ({
  appScope: { dispose: mocks.appScopeDispose },
}));

const emptySummary: ActiveSessionSummary = {
  acpSessions: 0,
  localTuiSessions: 0,
  remoteSessions: 0,
  terminals: 0,
  incomplete: false,
};

afterEach(() => {
  vi.useRealTimers();
  mocks.updateService.isInstallRequested = false;
});

describe('quit cleanup phases', () => {
  it('closes the database after app scope and before telemetry', async () => {
    configureQuitCleanupServices({
      editorBuffers: { dispose: mocks.editorBuffersDispose },
      projects: {
        dispose: mocks.projectsDispose,
        release: mocks.projectsRelease,
      },
      pullRequests: { dispose: mocks.pullRequestsDispose },
      runtimes: { dispose: mocks.runtimesDispose },
    });

    await runQuitCleanup();

    expect(mocks.closeAppDb).toHaveBeenCalledOnce();
    expect(mocks.editorBuffersDispose).toHaveBeenCalledOnce();
    expect(mocks.projectsRelease.mock.invocationCallOrder[0]!).toBeLessThan(
      mocks.runtimesDispose.mock.invocationCallOrder[0]!
    );
    expect(mocks.projectsRelease.mock.invocationCallOrder[0]!).toBeLessThan(
      mocks.projectsDispose.mock.invocationCallOrder[0]!
    );
    expect(mocks.appScopeDispose.mock.invocationCallOrder[0]!).toBeLessThan(
      mocks.closeAppDb.mock.invocationCallOrder[0]!
    );
    expect(mocks.closeAppDb.mock.invocationCallOrder[0]!).toBeLessThan(
      mocks.telemetryDispose.mock.invocationCallOrder[0]!
    );
    expect(mocks.closeAppDb.mock.invocationCallOrder[0]!).toBeLessThan(
      mocks.projectsDispose.mock.invocationCallOrder[0]!
    );
  });
});

describe('shutdown coordinator', () => {
  it('confirms, flushes, cleans up, and exits', async () => {
    const harness = createHarness();
    const pending = harness.coordinator.handleQuitRequested();
    const confirmation = await harness.nextEvent('quit-confirmation-requested');

    harness.coordinator.resolveQuitConfirmation(confirmation.requestId, true);
    await harness.nextEvent('shutdown-started');
    harness.coordinator.ackShutdownFlush();
    await pending;

    expect(harness.runCleanup).toHaveBeenCalledOnce();
    expect(harness.exit).toHaveBeenCalledWith(0);
    expect(harness.coordinator.state).toBe('shutting-down');
  });

  it('returns to idle without cleanup when confirmation is cancelled', async () => {
    const harness = createHarness();
    const pending = harness.coordinator.handleQuitRequested();
    const confirmation = await harness.nextEvent('quit-confirmation-requested');

    harness.coordinator.resolveQuitConfirmation(confirmation.requestId, false);
    await pending;

    expect(harness.events).toContainEqual({
      type: 'quit-confirmation-cancelled',
      requestId: confirmation.requestId,
    });
    expect(harness.runCleanup).not.toHaveBeenCalled();
    expect(harness.exit).not.toHaveBeenCalled();
    expect(harness.coordinator.state).toBe('idle');
  });

  it('proceeds after the confirmation deadline and ignores stale replies', async () => {
    vi.useFakeTimers();
    const harness = createHarness();
    const pending = harness.coordinator.handleQuitRequested();
    const confirmation = await harness.nextEvent('quit-confirmation-requested');

    await vi.advanceTimersByTimeAsync(60_000);
    await harness.nextEvent('shutdown-started');
    harness.coordinator.ackShutdownFlush();
    await pending;
    harness.coordinator.resolveQuitConfirmation(confirmation.requestId, true);

    expect(harness.events).toContainEqual({
      type: 'quit-confirmation-cancelled',
      requestId: confirmation.requestId,
    });
    expect(harness.runCleanup).toHaveBeenCalledOnce();
    expect(harness.coordinator.state).toBe('shutting-down');
  });

  it('skips renderer stages when the renderer has not registered', async () => {
    const harness = createHarness({ markReady: false });
    await harness.coordinator.handleQuitRequested();

    expect(harness.events).toEqual([]);
    expect(harness.runCleanup).toHaveBeenCalledOnce();
    expect(harness.exit).toHaveBeenCalledWith(0);
  });

  it('revokes renderer capability when the renderer starts loading', async () => {
    const harness = createHarness();
    harness.window.emitWebContents('did-start-loading');

    await harness.coordinator.handleQuitRequested();

    expect(harness.events).toEqual([]);
    expect(harness.runCleanup).toHaveBeenCalledOnce();
  });

  it('cancels a pending confirmation when the renderer starts loading', async () => {
    const harness = createHarness();
    const pending = harness.coordinator.handleQuitRequested();
    const confirmation = await harness.nextEvent('quit-confirmation-requested');

    harness.window.emitWebContents('did-start-loading');
    await pending;

    expect(harness.events).toContainEqual({
      type: 'quit-confirmation-cancelled',
      requestId: confirmation.requestId,
    });
    expect(harness.runCleanup).not.toHaveBeenCalled();
    expect(harness.coordinator.state).toBe('idle');
  });

  it('does not reuse a registration from an old window', async () => {
    const first = createFakeWindow(1);
    const second = createFakeWindow(2);
    const harness = createHarness({ window: first });
    harness.coordinator.watchWindow(second.window);

    await harness.coordinator.handleQuitRequested();

    expect(harness.events).toEqual([]);
    expect(harness.runCleanup).toHaveBeenCalledOnce();
  });

  it('continues cleanup when the renderer flush times out', async () => {
    vi.useFakeTimers();
    const harness = createHarness();
    const pending = harness.coordinator.handleQuitRequested();
    const confirmation = await harness.nextEvent('quit-confirmation-requested');
    harness.coordinator.resolveQuitConfirmation(confirmation.requestId, true);
    await harness.nextEvent('shutdown-started');

    await vi.advanceTimersByTimeAsync(2_000);
    await pending;

    expect(harness.runCleanup).toHaveBeenCalledOnce();
    expect(harness.exit).toHaveBeenCalledWith(0);
  });

  it('skips confirmation for an updater install but still flushes', async () => {
    const harness = createHarness({ installRequested: true });
    const pending = harness.coordinator.handleQuitRequested();
    await harness.nextEvent('shutdown-started');
    harness.coordinator.ackShutdownFlush();
    await pending;

    expect(harness.events.some((event) => event.type === 'quit-confirmation-requested')).toBe(
      false
    );
    expect(harness.runCleanup).toHaveBeenCalledOnce();
  });

  it('ignores re-entrant quit requests while confirming', async () => {
    const harness = createHarness();
    const first = harness.coordinator.handleQuitRequested();
    const confirmation = await harness.nextEvent('quit-confirmation-requested');
    expect(harness.coordinator.isShutdownInProgress()).toBe(true);
    await harness.coordinator.handleQuitRequested();

    expect(
      harness.events.filter((event) => event.type === 'quit-confirmation-requested')
    ).toHaveLength(1);
    harness.coordinator.resolveQuitConfirmation(confirmation.requestId, false);
    await first;
    expect(harness.coordinator.isShutdownInProgress()).toBe(false);
  });

  it('proceeds when an updater install is requested while confirming', async () => {
    const harness = createHarness();
    const first = harness.coordinator.handleQuitRequested();
    const confirmation = await harness.nextEvent('quit-confirmation-requested');

    harness.setInstallRequested(true);
    await harness.coordinator.handleQuitRequested();
    await harness.nextEvent('shutdown-started');
    harness.coordinator.ackShutdownFlush();
    await first;

    expect(harness.events).toContainEqual({
      type: 'quit-confirmation-cancelled',
      requestId: confirmation.requestId,
    });
    expect(harness.runCleanup).toHaveBeenCalledOnce();
    expect(harness.exit).toHaveBeenCalledWith(0);
  });

  it('shows a hidden window before requesting confirmation', async () => {
    const harness = createHarness();
    const pending = harness.coordinator.handleQuitRequested();
    const confirmation = await harness.nextEvent('quit-confirmation-requested');

    expect(harness.window.show).toHaveBeenCalledOnce();
    expect(harness.window.focus).toHaveBeenCalledOnce();
    harness.coordinator.resolveQuitConfirmation(confirmation.requestId, false);
    await pending;
  });

  it('forces exit at the hard deadline', async () => {
    vi.useFakeTimers();
    let finishCleanup!: () => void;
    const cleanup = new Promise<void>((resolve) => {
      finishCleanup = resolve;
    });
    const harness = createHarness({ runCleanup: () => cleanup });
    const pending = harness.coordinator.handleQuitRequested();
    const confirmation = await harness.nextEvent('quit-confirmation-requested');
    harness.coordinator.resolveQuitConfirmation(confirmation.requestId, true);
    await harness.nextEvent('shutdown-started');
    harness.coordinator.ackShutdownFlush();
    await Promise.resolve();

    await vi.advanceTimersByTimeAsync(8_000);
    expect(harness.exit).toHaveBeenCalledWith(0);

    finishCleanup();
    await pending;
    expect(harness.exit).toHaveBeenCalledOnce();
  });

  it('allows a window to close when an updater install is pending', () => {
    expect(shouldAllowWindowClose()).toBe(false);

    mocks.updateService.isInstallRequested = true;

    expect(shouldAllowWindowClose()).toBe(true);
  });
});

interface FakeWindow {
  readonly window: BrowserWindow;
  readonly show: ReturnType<typeof vi.fn>;
  readonly focus: ReturnType<typeof vi.fn>;
  emitWebContents(event: string): void;
}

function createFakeWindow(id: number): FakeWindow {
  const webContentsListeners = new Map<string, () => void>();
  const windowListeners = new Map<string, () => void>();
  const show = vi.fn();
  const focus = vi.fn();
  const window = {
    isDestroyed: () => false,
    isMinimized: () => false,
    restore: vi.fn(),
    show,
    focus,
    webContents: {
      id,
      isDestroyed: () => false,
      on: (event: string, listener: () => void) => {
        webContentsListeners.set(event, listener);
      },
    },
    on: (event: string, listener: () => void) => {
      windowListeners.set(event, listener);
    },
  } as unknown as BrowserWindow;
  return {
    window,
    show,
    focus,
    emitWebContents: (event) => webContentsListeners.get(event)?.(),
  };
}

function createHarness(
  options: {
    installRequested?: boolean;
    markReady?: boolean;
    window?: FakeWindow;
    runCleanup?: () => Promise<void>;
  } = {}
) {
  const events: DesktopHostEvent[] = [];
  const fakeWindow = options.window ?? createFakeWindow(1);
  const runCleanup = vi.fn(options.runCleanup ?? (async () => {}));
  const exit = vi.fn();
  let installRequested = options.installRequested ?? false;
  const dependencies: ShutdownCoordinatorDependencies = {
    emit: (event) => events.push(event),
    getActiveSessionSummary: async () => emptySummary,
    isInstallRequested: () => installRequested,
    runCleanup,
    exit,
  };
  const coordinator = createShutdownCoordinator(dependencies);
  coordinator.watchWindow(fakeWindow.window);
  if (options.markReady !== false) coordinator.markShutdownReady();

  return {
    coordinator,
    events,
    runCleanup,
    exit,
    window: fakeWindow,
    setInstallRequested(value: boolean): void {
      installRequested = value;
    },
    async nextEvent<TType extends DesktopHostEvent['type']>(
      type: TType
    ): Promise<Extract<DesktopHostEvent, { type: TType }>> {
      for (let attempt = 0; attempt < 10; attempt += 1) {
        const event = events.find(
          (candidate): candidate is Extract<DesktopHostEvent, { type: TType }> =>
            candidate.type === type
        );
        if (event) return event;
        await Promise.resolve();
      }
      throw new Error(`Expected event '${type}'`);
    },
  };
}
