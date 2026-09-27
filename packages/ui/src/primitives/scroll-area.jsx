import * as React from "react"
import { ScrollArea as ScrollAreaPrimitive } from "radix-ui"

import { cn } from "@hardcore/ui/utils"

/**
 * The one scroll region of the viewer's chrome (shadcn's ScrollArea): thin overlay bars in the
 * theme's colours, shown while the pointer is over the region, in place of the platform's.
 *
 * The root is a flex column and the viewport its `min-h-0 flex-1` item, so a region bounded only
 * by a max-height (a panel's cap, a menu's available height) scrolls inside it instead of
 * growing past it. `viewportRef` and `viewportProps` reach the element that actually scrolls, for
 * code that reads or sets its scroll position, focuses it or gives it a role. `orientation`:
 * `"vertical"` (the default) lays content out at the region's width, so rows truncate;
 * `"both"` lets wide content scroll sideways too. `scrollbar={false}`: no visible bar, for a region
 * whose bar would stand outside what it holds (the tool stack's column); the wheel, a trackpad and the keyboard still scroll.
 * The bar stays mounted, hidden: the primitive lets its viewport scroll on an axis only while that
 * axis has a bar, and clips it otherwise.
 */
const ScrollArea = React.forwardRef(function ScrollArea({
  className,
  viewportClassName,
  viewportRef,
  viewportProps,
  orientation = "vertical",
  scrollbar = true,
  children,
  ...props
}, ref) {
  return (
    <ScrollAreaPrimitive.Root
      ref={ref}
      className={cn("relative flex min-h-0 flex-col overflow-hidden", className)}
      {...props}
      // After the props: a trigger wrapping the region (`asChild`) names its own slot, and the
      // region is still a scroll area.
      data-slot="scroll-area"
    >
      <ScrollAreaPrimitive.Viewport
        ref={viewportRef}
        data-slot="scroll-area-viewport"
        {...viewportProps}
        className={cn(
          "min-h-0 w-full flex-1 rounded-[inherit] outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/45",
          // The primitive lays its content out as a table, as wide as it likes; a vertical region
          // holds it to its own width instead.
          orientation === "vertical" && "[&>div]:!block",
          viewportClassName
        )}
      >
        {children}
      </ScrollAreaPrimitive.Viewport>
      {orientation !== "horizontal" ? <ScrollBar className={scrollbar ? undefined : "invisible"} /> : null}
      {orientation !== "vertical" ? <ScrollBar orientation="horizontal" className={scrollbar ? undefined : "invisible"} /> : null}
      <ScrollAreaPrimitive.Corner />
    </ScrollAreaPrimitive.Root>
  )
})

function ScrollBar({
  className,
  orientation = "vertical",
  ...props
}) {
  return (
    <ScrollAreaPrimitive.ScrollAreaScrollbar
      data-slot="scroll-area-scrollbar"
      orientation={orientation}
      className={cn(
        "flex touch-none p-px transition-colors select-none",
        orientation === "vertical" &&
          "h-full w-2 border-l border-l-transparent",
        orientation === "horizontal" &&
          "h-2 flex-col border-t border-t-transparent",
        className
      )}
      {...props}
    >
      <ScrollAreaPrimitive.ScrollAreaThumb
        data-slot="scroll-area-thumb"
        className="relative flex-1 rounded-full bg-border hover:bg-muted-foreground/50"
      />
    </ScrollAreaPrimitive.ScrollAreaScrollbar>
  )
}

export { ScrollArea, ScrollBar }
