/**
 * The surfaces of everything that floats over the model, defined here once so they cannot drift
 * apart; a caller adds layout, never a surface of its own. All three are the popover's colour, a
 * step off the app's own background (a step lighter in the dark theme), nearly opaque, with a border
 * and a shadow: they read as chrome over any canvas, a flat view's (the app's background, which a
 * surface of that colour vanishes into) and a 3D scene's alike, and the model under them stays out of
 * their way rather than showing through.
 *
 * `FLOATING_CHROME_SURFACE_CLASS`: the tool strip, its sub-toolbars, the tool stack's panels and a
 * collapsed panel's pill, up beside the model for as long as a file is open: 90%, a small blur and a
 * medium shadow, so the strip stands off the canvas.
 * `FILE_SIDEBAR_SURFACE_CLASS`: the file sidebar's panel, mostly text, up for as long as a file is
 * open: 92%, a small blur.
 * `FLOATING_SURFACE_CLASS`: the popovers and menus opened over the viewport (a mode menu, the
 * viewport's context menu, the app menu, the explorer, Display's settings, the Animation section's
 * Playback settings) — read while they are up: 95%, blurred.
 */
export const FLOATING_SURFACE_CLASS = "border border-border bg-popover/95 text-foreground shadow-sm backdrop-blur-md";
export const FILE_SIDEBAR_SURFACE_CLASS = "border border-border bg-popover/92 text-foreground shadow-sm backdrop-blur-sm";
export const FLOATING_CHROME_SURFACE_CLASS = "border border-border bg-popover/90 text-foreground shadow-md backdrop-blur-sm";
