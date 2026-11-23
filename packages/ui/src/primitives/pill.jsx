import * as React from "react";
import { cn } from "@cad/ui/utils";

// THE pill (`docs/design-system.md`, "Pills and the segmented control"): the panel's tab pill, the control tall, 6px in
// at each side, `rounded-md`, the scale's `text-ui`. The one on is `bg-accent` with the foreground at medium weight; the
// others are muted, with `bg-accent/50` under the pointer. A row of pills is one choice of several: the panel's tabs, the
// home's kinds.

/** The pill's look, on or off by `aria-pressed` (a toggle) or `aria-selected` (a tab). */
export const PILL_CLASS = "flex h-control shrink-0 items-center whitespace-nowrap rounded-md px-1.5 text-ui transition-colors "
  + "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45";
export const PILL_ON_CLASS = "bg-accent text-foreground";
export const PILL_OFF_CLASS = "text-muted-foreground hover:bg-accent/50 hover:text-foreground";

/**
 * A pill that is a toggle of a row of them (`aria-pressed`): its name, as wide as at medium weight so turning it on moves
 * nothing, then its count where it has one, muted, regular and tabular, 4px on.
 */
export const Pill = React.forwardRef(/**
 * @param {React.ComponentPropsWithoutRef<"button"> & { pressed: boolean, count?: React.ReactNode }} props
 * @param {React.ForwardedRef<HTMLButtonElement>} ref
 */ function Pill({ pressed, count = null, className, children, ...props }, ref) {
  return <button ref={ref} type="button" aria-pressed={pressed} data-slot="pill" className={cn(PILL_CLASS, pressed ? PILL_ON_CLASS : PILL_OFF_CLASS, "gap-1", className)} {...props}>
    <span className="grid">
      <span aria-hidden="true" className="invisible col-start-1 row-start-1 font-medium">{children}</span>
      <span className={cn("col-start-1 row-start-1", pressed && "font-medium")}>{children}</span>
    </span>
    {count === null ? null : <span className="font-normal tabular-nums text-muted-foreground" data-pill-count="">{count}</span>}
  </button>;
});
