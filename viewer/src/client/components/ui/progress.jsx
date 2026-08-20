import * as React from "react"
import { Progress as ProgressPrimitive } from "radix-ui"

import { cn } from "@/ui/utils"

/**
 * shadcn/ui Progress, smui-styled.
 *
 * smui rules that apply here: zero border radius (`--radius: 0`), the frost-blue
 * `--primary` as the fill, and a muted track. The track is deliberately thin — this sits
 * over a live 3D scene, so it reads as a status line rather than a widget.
 *
 * `value` of `null` is INDETERMINATE per the radix contract, and callers that have no
 * denominator SHOULD pass it. A sliding bar says "working, no estimate" honestly; the
 * alternative — inventing a number so the bar always has one — is how a ten-minute phase
 * came to display a confident 0%.
 */
function Progress({ className, value, ...props }) {
  const clamped = Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : null;
  const indeterminate = clamped === null;
  return (
    <ProgressPrimitive.Root
      data-slot="progress"
      value={clamped}
      className={cn("relative h-[3px] w-full overflow-hidden bg-primary/20", className)}
      {...props}
    >
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        data-indeterminate={indeterminate ? "true" : undefined}
        className={cn(
          "h-full bg-primary",
          indeterminate
            ? "w-1/3 cad-progress-indeterminate"
            : "w-full flex-1 transition-transform duration-200 ease-out"
        )}
        style={indeterminate ? undefined : { transform: `translateX(-${100 - clamped}%)` }}
      />
    </ProgressPrimitive.Root>
  );
}

export { Progress }
