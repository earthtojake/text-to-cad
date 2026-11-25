/**
 * The surfaces of everything that floats over the model, defined here once so they cannot drift
 * apart; a caller adds layout, never a surface of its own. All of them are the popover's colour, a
 * step off the app's own background (a step lighter in the dark theme), nearly opaque, with a border
 * and a shadow: they read as chrome over any canvas, a flat view's (the app's background, which a
 * surface of that colour vanishes into) and a 3D scene's alike, and the model under them stays out of
 * their way rather than showing through.
 *
 * `FLOATING_CHROME_SURFACE_CLASS`: the tool strip, its sub-toolbars, the tool stack's panels, the bar over
 * picked ink and Quick Edit's bar, up beside the model for as long as a file is open: 90%, a small blur and a
 * medium shadow, so they stand off the canvas as one kind of thing. (A flat view's zoom in the corner is not: it
 * is on a faint surface of its own, `ZoomControl.jsx`.)
 * `FLOATING_SURFACE_CLASS`: the popovers and menus opened over the viewport (a mode menu, the
 * viewport's context menu, the app menu, the explorer, a settings card's dropdowns, a chip's card, Preview's
 * playbar's menus) — read while they are up: 95%, blurred.
 * `QUIET_CHROME_SURFACE_CLASS`: the chrome's surface stepped back — 70%, its border faint, no shadow — for
 * chrome up for as long as a file is open and seldom used, its controls always at full strength (never
 * dimmed). Nothing draws it now: the tools view has no playbar (its routines are the panel's Animation tab), and
 * Preview's playbar, the only one, is a transparent row (`kit/tools/playbar/PreviewPlaybar.jsx`).
 */
export const FLOATING_SURFACE_CLASS = "border border-border bg-popover/95 text-foreground shadow-sm backdrop-blur-md";
export const FLOATING_CHROME_SURFACE_CLASS = "border border-border bg-popover/90 text-foreground shadow-md backdrop-blur-sm";
export const QUIET_CHROME_SURFACE_CLASS = "border border-border/60 bg-popover/70 text-foreground shadow-none backdrop-blur-sm";
