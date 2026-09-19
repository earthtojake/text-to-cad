"use client"

import { cn } from "@hardcore/ui/utils"

function ScrollArea({
  className,
  viewportClassName,
  scrollbars = "vertical",
  type: _type,
  scrollHideDelay: _scrollHideDelay,
  children,
  ...props
}) {
  const scrollbarOrientations = Array.isArray(scrollbars)
    ? scrollbars
    : [scrollbars].filter(Boolean);
  const hasHorizontalScrollbar = scrollbarOrientations.includes("horizontal");
  const hasVerticalScrollbar = scrollbarOrientations.includes("vertical");
  const overflowX = hasHorizontalScrollbar ? "overflow-x-auto" : "overflow-x-hidden";
  const overflowY = hasVerticalScrollbar ? "overflow-y-auto" : "overflow-y-hidden";

  return (
    <div data-slot="scroll-area" className={cn("relative", className)} {...props}>
      <div
        data-slot="scroll-area-viewport"
        className={cn(
          "size-full rounded-[inherit] transition-[color,box-shadow] outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-1",
          overflowX,
          overflowY,
          viewportClassName
        )}>
        <div className={cn("min-w-full", hasHorizontalScrollbar ? "w-max" : "w-full")}>
          {children}
        </div>
      </div>
    </div>
  );
}

function ScrollBar({
  className: _className,
  orientation: _orientation = "vertical",
  ..._props
}) {
  return null;
}

export { ScrollArea, ScrollBar }
