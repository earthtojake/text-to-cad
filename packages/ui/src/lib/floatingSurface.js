/**
 * The surfaces of everything that floats over the model, defined here once so they cannot drift
 * apart; a caller adds layout, never a surface of its own. All of them are the popover's colour, a
 * step off the app's own background (a step lighter in the dark theme), nearly opaque, with a border
 * and a shadow: they read as chrome over any canvas, a flat view's (the app's background, which a
 * surface of that colour vanishes into) and a 3D scene's alike, and the model under them stays out of
 * their way rather than showing through.
 *
 * `FLOATING_CHROME_SURFACE_CLASS`: the tool strip, its sub-toolbars, the tool stack's panels, a
 * collapsed panel's pill and a flat view's zoom pill in the corner, up beside the model for as long as a
 * file is open: 90%, a small blur and a medium shadow, so they stand off the canvas as one kind of thing.
 * `FLOATING_SURFACE_CLASS`: the popovers and menus opened over the viewport (a mode menu, the
 * viewport's context menu, the app menu, the explorer, a settings card's dropdowns, a playbar's Playback
 * settings) — read while they are up: 95%, blurred.
 * `QUIET_CHROME_SURFACE_CLASS`: the tools view's playbar (`kit/tools/playbar/PlaybackBar.jsx`), up for
 * as long as a file with routines is open and seldom used: the chrome's surface stepped back — 70%,
 * its border faint, no shadow — its controls always at full strength (never dimmed).
 */
export const FLOATING_SURFACE_CLASS = "border border-border bg-popover/95 text-foreground shadow-sm backdrop-blur-md";
export const FLOATING_CHROME_SURFACE_CLASS = "border border-border bg-popover/90 text-foreground shadow-md backdrop-blur-sm";
export const QUIET_CHROME_SURFACE_CLASS = "border border-border/60 bg-popover/70 text-foreground shadow-none backdrop-blur-sm";
