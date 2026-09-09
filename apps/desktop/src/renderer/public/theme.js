/*
 * The colour scheme, before anything is parsed that could be painted.
 *
 * A classic script in `<head>`, from `public/`, so it runs while the document
 * is still being parsed — ahead of `readyState === "interactive"`, ahead of
 * the deferred module that boots React, and ahead of the first frame Chromium
 * can put on screen. `src/renderer/hooks/use-theme.ts` does the same write and
 * everything after it; this exists only for the frames before that file has
 * loaded, which is where the window used to flash white on a machine in dark.
 *
 * It cannot import — a classic script has no module graph — so the key, the
 * three ids and the two writes are repeated here. `tests/unit/renderer/
 * theme.test.ts` pins them against the module so the two cannot drift.
 * The standalone CAD Viewer has the same script for the same reason, inline in
 * its own `index.html`; this app's CSP forbids `unsafe-inline`, so it is a
 * file.
 *
 * The preference is a CACHE of the settings row in main's sqlite, never the
 * source of truth: the IPC read that follows corrects it, and `useApplyTheme`
 * writes it back.
 */
(function () {
  var root = document.documentElement;
  if (!root) {
    return;
  }
  var preference = "system";
  try {
    var stored = window.localStorage.getItem("hardcore.theme");
    if (stored === "system" || stored === "light" || stored === "dark") {
      preference = stored;
    }
  } catch {
    // A renderer with storage blocked still has an OS preference to follow.
  }
  var prefersDark = false;
  try {
    prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  } catch {
    /* see above */
  }
  var resolved = preference === "system" ? (prefersDark ? "dark" : "light") : preference;
  // The class is what Tailwind and shadcn compile against; `color-scheme` is
  // what the native scrollbars, the form controls and the window background
  // Electron paints behind the page follow.
  root.classList.toggle("dark", resolved === "dark");
  root.style.colorScheme = resolved;
})();
