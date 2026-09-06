import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type * as BootReport from './boot-report';

const logInfo = vi.fn();
const telemetryCapture = vi.fn();

vi.mock('@main/lib/logger', () => ({
  log: { info: (...args: unknown[]) => logInfo(...args), warn: vi.fn(), error: vi.fn() },
}));

vi.mock('@main/lib/telemetry', () => ({
  telemetryService: { capture: (...args: unknown[]) => telemetryCapture(...args) },
}));

async function flushDynamicImports(): Promise<void> {
  await vi.waitFor(() => expect(logInfo).toHaveBeenCalled());
  // The telemetry capture sits behind a dynamic import; give it a microtask.
  await vi.waitFor(() => expect(telemetryCapture).toHaveBeenCalled());
}

describe('boot-report', () => {
  let bootReport: typeof BootReport;

  beforeEach(async () => {
    vi.resetModules();
    vi.useFakeTimers();
    logInfo.mockClear();
    telemetryCapture.mockClear();
    bootReport = await import('./boot-report');
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('emits one report with both durations and phases once settled and usable', async () => {
    bootReport.recordBootPhase('window', 120);
    bootReport.recordBootPhase('database', 6);
    bootReport.recordWindowVisible(410);
    bootReport.notifyBootSettledForReport();
    expect(logInfo).not.toHaveBeenCalled();

    bootReport.recordUsableWorkspace(2740);
    await flushDynamicImports();

    expect(logInfo).toHaveBeenCalledExactlyOnceWith('boot-report', {
      windowVisibleMs: 410,
      usableWorkspaceMs: 2740,
      phases: { window: 120, database: 6 },
    });
    expect(telemetryCapture).toHaveBeenCalledExactlyOnceWith('app_started', {
      window_visible_ms: 410,
      usable_workspace_ms: 2740,
    });
  });

  it('emits when usable arrives before boot settles', async () => {
    bootReport.recordUsableWorkspace(2100);
    expect(logInfo).not.toHaveBeenCalled();

    bootReport.notifyBootSettledForReport();
    await flushDynamicImports();

    expect(logInfo).toHaveBeenCalledOnce();
  });

  it('emits without the usable duration after the grace period', async () => {
    bootReport.recordWindowVisible(400);
    bootReport.notifyBootSettledForReport();

    await vi.advanceTimersByTimeAsync(bootReport.BOOT_REPORT_GRACE_MS);
    await flushDynamicImports();

    expect(logInfo).toHaveBeenCalledExactlyOnceWith('boot-report', {
      windowVisibleMs: 400,
      usableWorkspaceMs: undefined,
      phases: {},
    });
    expect(telemetryCapture).toHaveBeenCalledExactlyOnceWith('app_started', {
      window_visible_ms: 400,
    });
  });

  it('never emits twice, even when the grace timer fires after emission', async () => {
    bootReport.notifyBootSettledForReport();
    bootReport.recordUsableWorkspace(3000);
    await flushDynamicImports();

    bootReport.recordUsableWorkspace(9999);
    await vi.advanceTimersByTimeAsync(bootReport.BOOT_REPORT_GRACE_MS);

    expect(logInfo).toHaveBeenCalledOnce();
    expect(telemetryCapture).toHaveBeenCalledOnce();
    expect(logInfo.mock.calls[0][1]).toMatchObject({ usableWorkspaceMs: 3000 });
  });

  it('keeps the first usable-workspace duration', async () => {
    bootReport.recordUsableWorkspace(2500);
    bootReport.recordUsableWorkspace(4000);
    bootReport.notifyBootSettledForReport();
    await flushDynamicImports();

    expect(logInfo.mock.calls[0][1]).toMatchObject({ usableWorkspaceMs: 2500 });
  });
});
