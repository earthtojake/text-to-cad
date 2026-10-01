/**
 * The numbers the quit tests share (README, "Quitting"): the e2e in `cad.spec.ts` asserts them
 * against a real app, `tests/unit/main/quit-sequence.test.ts` against the real `before-quit` handler.
 */

/** `app.quit()` to the pid being gone: the README's two seconds overall. */
export const QUIT_BUDGET_MS = 2_000;

/**
 * What `before-quit` may spend on its own teardown (the `[quit] teardown Nms` line).
 *
 * The teardown signals and closes and awaits nothing (README, "Quitting"), so it is
 * synchronous work: about 6 ms on a development machine, 15 ms on the 2.4x slower runner
 * that took 833 ms overall. The watchdog counts teardown toward the 1.2 s deadline, so
 * every millisecond here is one less for Chromium's shutdown. 250 ms is forty times the
 * local figure and a fifth of the deadline: slack enough for a loaded runner, tight enough
 * that a step that starts to wait (a `close()` that blocks, as chokidar's did for most of a
 * second) fails here and not as an unexplained total.
 */
export const QUIT_TEARDOWN_BUDGET_MS = 250;

/** The milliseconds in the `[quit] teardown Nms` line, or null if main has not logged one. */
export function teardownMs(lines: readonly string[]): number | null {
  for (const line of lines) {
    const match = /^\[quit\] teardown (\d+)ms$/.exec(line.trim());
    if (match) return Number(match[1]);
  }
  return null;
}
