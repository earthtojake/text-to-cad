import { log } from '@main/lib/logger';

/**
 * Per-launch boot report: aggregates the boot-timeline instrumentation into
 * one structured log line so any user's slow boot is diagnosable from their
 * log file, and attaches the two boot metrics to the `app_started` telemetry
 * event. Diagnostic only — no thresholds.
 *
 * The report emits once boot has settled (backend + window load, see
 * boot-status) and the renderer has reported its usable-workspace moment, or
 * after a grace period if that report never arrives (e.g. a crashed renderer).
 */

/** How long after boot settles to wait for the renderer's usable signal. */
export const BOOT_REPORT_GRACE_MS = 20_000;

const phases: Record<string, number> = {};
let windowVisibleMs: number | undefined;
let usableWorkspaceMs: number | undefined;
let settled = false;
let emitted = false;
let graceTimer: ReturnType<typeof setTimeout> | undefined;

/** Called by `step()` for every boot phase; last duration wins on retries. */
export function recordBootPhase(name: string, durationMs: number): void {
  if (emitted) return;
  phases[name] = durationMs;
}

/** Launch → window visible, from the actual `show()` in the window phase. */
export function recordWindowVisible(sinceProcessStartMs: number): void {
  windowVisibleMs ??= Math.round(sinceProcessStartMs);
}

/** Launch → usable workspace, from the renderer's splash-gate settling. */
export function recordUsableWorkspace(sinceProcessStartMs: number): void {
  usableWorkspaceMs ??= Math.round(sinceProcessStartMs);
  maybeEmit();
}

/** Hooked to `onBootSettled`; arms the grace timer for a missing renderer signal. */
export function notifyBootSettledForReport(): void {
  if (settled) return;
  settled = true;
  maybeEmit();
  if (emitted) return;
  graceTimer = setTimeout(() => emit(), BOOT_REPORT_GRACE_MS);
  graceTimer.unref?.();
}

function maybeEmit(): void {
  if (settled && usableWorkspaceMs !== undefined) emit();
}

function emit(): void {
  if (emitted) return;
  emitted = true;
  if (graceTimer !== undefined) clearTimeout(graceTimer);

  log.info('boot-report', {
    windowVisibleMs,
    usableWorkspaceMs,
    phases: { ...phases },
  });

  // Dynamic import keeps the telemetry module graph off the pre-window boot
  // path (this module is imported by core/phase.ts, which loads very early).
  void import('@main/lib/telemetry')
    .then(({ telemetryService }) => {
      // capture() is a no-op when telemetry is disabled.
      telemetryService.capture('app_started', {
        ...(windowVisibleMs !== undefined && { window_visible_ms: windowVisibleMs }),
        ...(usableWorkspaceMs !== undefined && { usable_workspace_ms: usableWorkspaceMs }),
      });
    })
    .catch((error: unknown) => {
      log.warn('boot-report: failed to capture app_started telemetry', { error });
    });
}
