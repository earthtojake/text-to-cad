// The navbar's row, in one place: its height, side padding and the gap between its icon buttons.
// Preview hides the navbar and draws its own controls at the view's top-right on a row of this
// same geometry, so its Playback settings and its way out land exactly where Settings and Preview
// sat in the navbar.
export const NAVBAR_ROW_CLASS = "flex h-9 shrink-0 items-center gap-2 border-b px-2";
// The icon buttons at the row's right end. Each 14px glyph keeps 5px around itself in its 24px
// button; the gap adds 4px, so two glyphs sit a glyph's width apart.
export const NAVBAR_CONTROLS_CLASS = "flex shrink-0 items-center gap-1";
