import { forwardRef } from "react";
import { Spline } from "lucide-react";
import { cn } from "@text-to-cad/ui/utils";

/**
 * The small dot (4px, as the dots of Position's own icon) in a tile's top-right corner while what the tile controls is off its default (an
 * effect on the model, a pose off the default, a routine's frame on the model). The tile is drawn
 * `relative` around it.
 */
export function ChangedDot({ className }) {
  return <span aria-hidden="true" data-tool-changed=""
    className={cn("pointer-events-none absolute right-[3px] top-[3px] size-1 rounded-full bg-primary", className)} />;
}

/**
 * Position's icon, everywhere it is drawn (the sidebar's tile and tab, Select's filter): lucide's
 * spline turned a quarter, so its top-right corner is clear for `ChangedDot`.
 */
export const PositionIcon = forwardRef(function PositionIcon({ className, ...props }, ref) {
  return <Spline ref={ref} className={cn("rotate-90", className)} {...props} />;
});
