import { activeBootSteps } from './phase';

/**
 * One generous timer armed at boot start that catches hung boots. On trigger
 * it reports the currently running boot phase to the injected handler —
 * nothing destructive happens here; the handler logs, reports telemetry, and
 * surfaces the renderer's escape hatch.
 */

const BOOT_WATCHDOG_TIMEOUT_MS = 60_000;

export type BootWatchdogTrigger = {
  /** The active `step()` stack (outermost first), or a placeholder when idle. */
  stuckPhase: string;
};

export type BootWatchdog = {
  disarm(): void;
};

export function shouldRecoverFromBootWatchdog(signals: { windowLoaded: boolean }): boolean {
  return !signals.windowLoaded;
}

export function startBootWatchdog(options: {
  onTrigger(trigger: BootWatchdogTrigger): void;
  timeoutMs?: number;
}): BootWatchdog {
  const timer = setTimeout(() => {
    const steps = activeBootSteps();
    const stuckPhase = steps.length > 0 ? steps.join(' > ') : '(no boot phase running)';
    options.onTrigger({ stuckPhase });
  }, options.timeoutMs ?? BOOT_WATCHDOG_TIMEOUT_MS);
  return {
    disarm: () => clearTimeout(timer),
  };
}
