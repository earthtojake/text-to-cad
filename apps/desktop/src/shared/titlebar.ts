/**
 * The one strip the window's own chrome shares with the app's.
 *
 * On macOS the window is `titleBarStyle: "hiddenInset"`: there is no title
 * bar, and AppKit draws the close/minimise/zoom buttons over the top-left of
 * whatever the renderer paints there. Two numbers have to agree for that to
 * work — where the buttons are (main, `trafficLightPosition`) and how much
 * room the leftmost pane leaves for them (`--titlebar-inset`, globals.css) —
 * so both are derived here rather than typed twice.
 *
 * The room is **measured, not assumed**. The buttons' width is AppKit's, not
 * ours: pinning their origin fixes where the cluster starts, never how wide it
 * is, and that has changed between macOS releases. Chromium already knows the
 * answer — with `titleBarOverlay` on, it publishes the region the window
 * controls occupy as the Window Controls Overlay geometry (the CSS
 * `env(titlebar-area-x)` and `navigator.windowControlsOverlay`) — so the
 * renderer reads it (`lib/titlebar.ts`) and `TRAFFIC_LIGHTS_INSET` is the
 * fallback for the frame before the first reading and for a window that has
 * no overlay at all.
 *
 * No Electron and no DOM here: main imports it for the window's options and
 * the renderer for the inset.
 */

/** The strip's height in CSS px. `--titlebar-height` in globals.css. */
export const TITLEBAR_HEIGHT = 36;

/** The distance from the window's left edge to the close button. */
export const TRAFFIC_LIGHT_X = 12;

/** AppKit draws each of the three buttons this tall (macOS 11 and later). */
export const TRAFFIC_LIGHT_DIAMETER = 12;

/**
 * The room the cluster needs on the left of the leftmost pane, in CSS px,
 * with the buttons pinned at `TRAFFIC_LIGHT_X`.
 *
 * Measured on macOS 15 (Electron 40) as the x of Chromium's titlebar-area
 * rect — the point past the window controls at which content may start. The
 * buttons themselves end a little before it; the difference is the same
 * margin AppKit leaves on their left. `globals.css` carries this number as
 * the CSS fallback, and `tests/e2e/titlebar.spec.ts` fails if the two drift.
 */
export const TRAFFIC_LIGHTS_INSET = 84;

/** Chromium's window-controls-overlay geometry, as the renderer sees it. */
export interface TitlebarOverlay {
  /** False in fullscreen, where macOS takes the buttons away entirely. */
  visible: boolean;
  /** Where the titlebar area starts: the room the controls need. */
  x: number;
}

/**
 * Where the traffic lights sit in the strip: vertically centred, so the row
 * of buttons the app draws beside them is level with them.
 */
export function trafficLightPosition(height: number = TITLEBAR_HEIGHT): { x: number; y: number } {
  return {
    x: TRAFFIC_LIGHT_X,
    y: Math.round((height - TRAFFIC_LIGHT_DIAMETER) / 2),
  };
}

/**
 * The inset the leftmost pane keeps clear, from a reading of the overlay.
 *
 * - no overlay (it has not been read yet, or the platform has none): the
 *   measured constant, because guessing zero puts a button under the lights;
 * - not visible (fullscreen): nothing, the lights are not there;
 * - visible: what Chromium reports, and the constant if that is somehow zero.
 */
export function titlebarInset(overlay: TitlebarOverlay | null | undefined): number {
  if (!overlay) {
    return TRAFFIC_LIGHTS_INSET;
  }
  if (!overlay.visible) {
    return 0;
  }
  const measured = Math.round(overlay.x);
  return measured > 0 ? measured : TRAFFIC_LIGHTS_INSET;
}
