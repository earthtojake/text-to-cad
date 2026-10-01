/**
 * How many browser specs (`*.browser.test.*`, each a Chromium doing WebGL) run at once.
 *
 * `requested` is `UI_BROWSER_TEST_CONCURRENCY` (4 unless set; CI sets 1). On a machine whose
 * one-minute load average already exceeds its core count, four more Chromiums push the WebGL
 * specs past their timeouts (three timed out at load 99), so they run one at a time instead.
 * On a quiet machine this changes nothing.
 */
export function chooseBrowserConcurrency({ requested, load, cpus }) {
  const wanted = Math.max(1, Number.parseInt(requested || "4", 10) || 4);
  if (wanted > 1 && load > cpus) {
    return {
      concurrency: 1,
      note: `machine is busy (load ${load.toFixed(1)} > ${cpus} cores): running browser specs at concurrency 1`,
    };
  }
  return { concurrency: wanted, note: null };
}
