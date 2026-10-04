// The navbar's row, in one place: its height, side padding and the gap between its icon buttons.
export const NAVBAR_ROW_CLASS = "flex h-9 shrink-0 items-center gap-2 border-b px-2";
// The icon buttons at the row's right end. Each 14px glyph keeps 5px around itself in its 24px
// button; the gap adds 4px, so two glyphs sit a glyph's width apart.
export const NAVBAR_CONTROLS_CLASS = "flex shrink-0 items-center gap-1";
// A view's own controls (Display and Preview on top of the cube, preview's) look as the navbar's icon buttons do.
export const NAVBAR_CONTROL_CLASS = "size-6 text-muted-foreground hover:text-foreground aria-pressed:bg-accent aria-pressed:text-accent-foreground";
