// THE pill (`docs/design-system.md`, "Pills and the segmented control"): the panel's tab pill, the control tall, 6px in
// at each side, `rounded-md`, the scale's `text-ui`. The panel's tabs draw it, on or off by `aria-selected`, in
// `renderers/kit/shell/FlatPanel.jsx`.

/** The pill's look; the tab on is `bg-accent` with the foreground at medium weight, the others muted. */
export const PILL_CLASS = "flex h-control shrink-0 items-center whitespace-nowrap rounded-md px-1.5 text-ui transition-colors "
  + "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45";
