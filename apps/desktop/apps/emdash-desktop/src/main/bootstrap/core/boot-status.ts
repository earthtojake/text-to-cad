/**
 * Aggregates the two boot success signals under the window-first boot: the
 * backend chain finishing (`finishBoot` resolved) and the main window's
 * `did-finish-load`. Either alone leaves a real failure uncounted — a visible
 * window with a dead backend, or a healthy backend behind a window that never
 * rendered — so boot only "settles" (and the crash-loop marker only clears)
 * once both have fired.
 */

export type BootSuccessSignal = 'backend' | 'window-load';

const seen = new Set<BootSuccessSignal>();
let settled = false;
const settledCallbacks: Array<() => void> = [];

export function reportBootSuccessSignal(signal: BootSuccessSignal): void {
  if (settled) return;
  seen.add(signal);
  if (!seen.has('backend') || !seen.has('window-load')) return;
  settled = true;
  for (const callback of settledCallbacks.splice(0)) callback();
}

export function isBootSettled(): boolean {
  return settled;
}

export function bootSuccessSignalsSeen(): { backend: boolean; windowLoaded: boolean } {
  return { backend: seen.has('backend'), windowLoaded: seen.has('window-load') };
}

/** Runs once when both signals have fired; immediately if already settled. */
export function onBootSettled(callback: () => void): void {
  if (settled) {
    callback();
    return;
  }
  settledCallbacks.push(callback);
}
