/**
 * The one surface of everything that floats over the model: the tool strip, each panel of the
 * tool stack, and the popovers and menus opened from them (Display, a tool's corner menu, the
 * viewport's context menu). Translucent and blurred, so the model reads through without the
 * text losing to it, with a border that keeps the edge on a light scene and a dark one alike.
 * Defined once so they cannot drift apart; a caller adds layout, never a surface of its own.
 */
export const FLOATING_SURFACE_CLASS = "border border-border bg-background/75 text-foreground shadow-sm backdrop-blur-md";
