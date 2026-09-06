/**
 * The boot splash gate: decides when the single boot loading state ends.
 *
 * The splash lifts when the last-active view can render — mementos and
 * navigation restored and the one
 * Project that view needs hydrated from desktop state — raced against a short
 * timer. Host readiness and attachment continue independently behind the gate.
 */

export type SplashGateOutcome = 'ready' | 'timeout';

export const SPLASH_GATE_TIMEOUT_MS = 3000;

/**
 * Races the gate conditions against the splash deadline. A rejected condition
 * counts as settled: an errored dependency must surface its product error
 * state behind a lifted splash, never hold the splash forever.
 */
export function raceSplashGate(
  conditions: readonly Promise<unknown>[],
  timeoutMs: number
): Promise<SplashGateOutcome> {
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve('timeout'), timeoutMs);
    void Promise.allSettled(conditions).then(() => {
      clearTimeout(timer);
      resolve('ready');
    });
  });
}

export async function waitForActiveProjectContext(options: {
  navigationRestored: Promise<unknown>;
  projectsLoaded: Promise<unknown>;
  activeProjectId: () => string | undefined;
  hydrateProjectContext: (projectId: string) => Promise<unknown>;
}): Promise<void> {
  await options.navigationRestored;
  const projectId = options.activeProjectId();
  if (!projectId) return;
  await options.projectsLoaded;
  await options.hydrateProjectContext(projectId);
}
