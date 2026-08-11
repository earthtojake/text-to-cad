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
 * `value` of `null` is INDETERMINATE per the radix contract. Callers that have no real
 * denominator should still pass a number (an estimate) rather than null, so the bar always
 * moves; see `estimatedLoadingRatio` in workbench/artifactProgress.js.
 */
function Progress({ className, value, ...props }) {
  const clamped = Number.isFinite(value) ? Math.min(100, Math.max(0, value)) : null;
  return (
    <ProgressPrimitive.Root
      data-slot="progress"
      value={clamped}
      className={cn("relative h-[3px] w-full overflow-hidden bg-primary/20", className)}
      {...props}
    >
      <ProgressPrimitive.Indicator
        data-slot="progress-indicator"
        className="h-full w-full flex-1 bg-primary transition-transform duration-200 ease-out"
        style={{ transform: `translateX(-${100 - (clamped ?? 0)}%)` }}
      />
    </ProgressPrimitive.Root>
  );
}

export { Progress }
