// The navbar's row, in one place: its height, side padding and the gap between its icon buttons.
// The control and 12px (40px on a desktop, 48 on a phone: THE scale, `globals.css`), the floating tool strip's height,
// its controls the strip's buttons, centred in it.
export const NAVBAR_ROW_CLASS = "flex h-[calc(var(--cad-control)+12px)] shrink-0 items-center gap-2 border-b px-2";
// The icon buttons at the row's right end, the control each, as the strip's and the panel head's are; the
// gap adds 4px.
export const NAVBAR_CONTROLS_CLASS = "flex shrink-0 items-center gap-1";
// An icon button on the navbar's row: the navbar's own (Export), and those of Preview's bar, which
// Preview draws in the navbar's place.
export const NAVBAR_CONTROL_CLASS = "size-control text-muted-foreground hover:text-foreground aria-pressed:bg-accent aria-pressed:text-accent-foreground";
