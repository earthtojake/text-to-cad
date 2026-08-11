import * as React from "react"
import { Popover as PopoverPrimitive } from "radix-ui"

import { cn } from "@/ui/utils"

function Popover({
  ...props
}) {
  return <PopoverPrimitive.Root data-slot="popover" {...props} />
}

const PopoverTrigger = React.forwardRef(function PopoverTrigger({
  ...props
}, ref) {
  return <PopoverPrimitive.Trigger ref={ref} data-slot="popover-trigger" {...props} />
});

// Positions a popover against an element that is not its trigger — used by
// coach marks, which point at a control the user still has to be able to click.
const PopoverAnchor = React.forwardRef(function PopoverAnchor({
  ...props
}, ref) {
  return <PopoverPrimitive.Anchor ref={ref} data-slot="popover-anchor" {...props} />
});

// `glass={false}` drops the shared glass surface and its default foreground.
// .cad-glass-popover sets background-color with !important, so a caller that
// wants its own surface has to opt out here rather than override it.
const PopoverContent = React.forwardRef(function PopoverContent({
  className,
  align = "center",
  sideOffset = 4,
  glass = true,
  ...props
}, ref) {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        ref={ref}
        data-slot="popover-content"
        align={align}
        sideOffset={sideOffset}
        className={cn(
          "z-50 w-72 origin-(--radix-popover-content-transform-origin) rounded-md border p-4 shadow-md outline-none data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 data-[side=bottom]:slide-in-from-top-2 data-[side=left]:slide-in-from-right-2 data-[side=right]:slide-in-from-left-2 data-[side=top]:slide-in-from-bottom-2",
          glass && "cad-glass-popover text-popover-foreground",
          className
        )}
        {...props}
      />
    </PopoverPrimitive.Portal>
  )
});

export { Popover, PopoverAnchor, PopoverContent, PopoverTrigger }
