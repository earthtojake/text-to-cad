// The navbar's row, in one place: its height, side padding and the gap between its icon buttons.
// 40px, the floating tool strip's height, its controls the strip's 28px buttons, centred in it.
export const NAVBAR_ROW_CLASS = "flex h-10 shrink-0 items-center gap-2 border-b px-2";
// The icon buttons at the row's right end, 28px each, as the strip's and the panel head's are; the
// gap adds 4px.
export const NAVBAR_CONTROLS_CLASS = "flex shrink-0 items-center gap-1";
// An icon button on the navbar's row: the navbar's own (Export), and those of Preview's bar, which
// Preview draws in the navbar's place.
export const NAVBAR_CONTROL_CLASS = "size-7 text-muted-foreground hover:text-foreground aria-pressed:bg-accent aria-pressed:text-accent-foreground";
