/**
 * How the CAD surface is laid out inside the explorer's pane.
 *
 * The viewer's own layout is measured against its root and drops into compact
 * mode — its file sheet as a drawer over the model — below 1024px. Every
 * explorer pane is narrower than that, so the desktop pins the desktop
 * layout (`layout="desktop"`, apps/viewer/docs/file-view.md); and its panels
 * are drawn in the file tab's own panel column (`panelSlot`), so their width
 * is the column's and nothing here has an opinion about it. What used to be
 * here — a share-of-the-pane sheet width, and a rule that hid the file tree
 * for a CAD file because a model, a sheet and a tree did not fit — went with
 * it: one panel is open at a time now, so there is nothing to fit.
 */

/**
 * The scene's backdrop: the app's own `--background`, so a model sits on the
 * same ground as the chrome around it instead of in a framed studio. The
 * tokens are shadcn's neutral pair (`oklch(1 0 0)` / `oklch(0.145 0 0)`); the
 * viewer's theme model takes hex, so they are written out here.
 */
export function cadSceneBackgroundFor(colorScheme: "light" | "dark"): string {
  return colorScheme === "dark" ? "#0a0a0a" : "#ffffff";
}
