/**
 * The surfaces of everything that floats over the model, defined here once so they cannot drift
 * apart; a caller adds layout, never a surface of its own. Both are translucent and blurred, so the
 * model reads through without the text losing to it, with a border that keeps the edge on a light
 * scene and a dark one alike.
 *
 * `FLOATING_SURFACE_CLASS`: the popovers and menus opened over the viewport (a mode menu, the
 * viewport's context menu, the app menu, the explorer, Display's settings, the Animation section's Playback settings) — read while
 * they are up, and opaque enough that their text never competes with the model.
 * `FILE_SIDEBAR_SURFACE_CLASS`: the file sidebar, mostly text, up for as long as a file is open:
 * between the two, the background at 55% and lightly blurred (4px).
 * `FLOATING_CHROME_SURFACE_CLASS`: the tool strip, its sub-toolbars and each panel of the tool
 * stack, which stay up beside the model for as long as a file is open: the background at 30% and
 * barely blurred (1px), so the model behind them is easy to make out, with the same border.
 */
export const FLOATING_SURFACE_CLASS = "border border-border bg-background/75 text-foreground shadow-sm backdrop-blur-md";
export const FILE_SIDEBAR_SURFACE_CLASS = "border border-border bg-background/55 text-foreground shadow-sm backdrop-blur-[4px]";
export const FLOATING_CHROME_SURFACE_CLASS = "border border-border bg-background/30 text-foreground shadow-sm backdrop-blur-[1px]";
