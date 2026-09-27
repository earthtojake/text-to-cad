/**
 * The surfaces of everything that floats over the model, defined here once so they cannot drift
 * apart; a caller adds layout, never a surface of its own. Both are translucent and blurred, so the
 * model reads through without the text losing to it, with a border that keeps the edge on a light
 * scene and a dark one alike.
 *
 * `FLOATING_SURFACE_CLASS`: the popovers and menus opened over the viewport (a mode menu, the
 * viewport's context menu, Display's settings, preview's Playback settings) — small, read while they are
 * up, and opaque enough that their text never competes with the model.
 * `FLOATING_CHROME_SURFACE_CLASS`: the tool strip and each panel of the tool stack, which stay up
 * beside the model for as long as a file is open: light enough, and barely blurred, that the model
 * behind them is easy to make out, with the same border.
 */
export const FLOATING_SURFACE_CLASS = "border border-border bg-background/75 text-foreground shadow-sm backdrop-blur-md";
export const FLOATING_CHROME_SURFACE_CLASS = "border border-border bg-background/35 text-foreground shadow-sm backdrop-blur-[2px]";
