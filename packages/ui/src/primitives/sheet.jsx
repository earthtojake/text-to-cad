"use client"

import * as React from "react"
import { Dialog as SheetPrimitive } from "radix-ui"
import { XIcon } from "lucide-react"

import { cn } from "@cad/ui/utils"

// shadcn's Sheet as shipped (Radix's Dialog drawn from an edge), with no window breakpoints (`docs/design-system.md`, "Dialogs and sheets"): a side
// sheet is 3/4 of the window wide and never wider than 20rem. Additions: `onSwipeClose`, where a finger swiped
// towards the sheet's own edge closes it (a phone's sidebar is put away the way it came), which Radix's Dialog has none of;
// and, for a sheet that is part of the page rather than a step out of it (a phone's sidebar), `scrim={false}` (its overlay
// kept but clear: a press beside the sheet still lands on it and closes the sheet, and reaches nothing under it),
// `animated={false}` (none of shadcn's slide and fade: it appears and goes at once, unless its classes bring a motion
// of their own, as the phone's sidebar brings the peek's, `file-viewer/panelPeek.js`) and `overlayStyle` (where the
// overlay starts).

/** @param {React.ComponentProps<typeof SheetPrimitive.Root>} props */
function Sheet({ ...props }) {
  return <SheetPrimitive.Root data-slot="sheet" {...props} />
}

/** @param {React.ComponentProps<typeof SheetPrimitive.Trigger>} props */
function SheetTrigger({ ...props }) {
  return <SheetPrimitive.Trigger data-slot="sheet-trigger" {...props} />
}

/** @param {React.ComponentProps<typeof SheetPrimitive.Close>} props */
function SheetClose({ ...props }) {
  return <SheetPrimitive.Close data-slot="sheet-close" {...props} />
}

/** @param {React.ComponentProps<typeof SheetPrimitive.Portal>} props */
function SheetPortal({ ...props }) {
  return <SheetPrimitive.Portal data-slot="sheet-portal" {...props} />
}

/** @param {React.ComponentProps<typeof SheetPrimitive.Overlay> & { scrim?: boolean, animated?: boolean }} props */
function SheetOverlay({ className, scrim = true, animated = true, ...props }) {
  return (
    <SheetPrimitive.Overlay
      data-slot="sheet-overlay"
      data-scrim={scrim ? "" : undefined}
      className={cn(
        "fixed inset-0 z-50",
        scrim && "bg-black/50",
        animated && "data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0",
        className
      )}
      {...props}
    />
  )
}

// A swipe this far towards the sheet's edge, more across than along it, closes it.
const SWIPE_CLOSE_PX = 48

/**
 * @param {React.ComponentProps<typeof SheetPrimitive.Content> & { side?: "top" | "right" | "bottom" | "left",
 *   showCloseButton?: boolean, closeLabel?: string, onSwipeClose?: (() => void) | null, container?: HTMLElement | null,
 *   scrim?: boolean, animated?: boolean, overlayStyle?: React.CSSProperties }} props
 *   `container`: its portal's, where the sheet must stand inside an element (the viewer's, whose phone styles reach it).
 */
function SheetContent({ className, children, side = "right", showCloseButton = true, closeLabel = "Close", onSwipeClose = null, container = undefined,
  scrim = true, animated = true, overlayStyle = undefined, ...props }) {
  const start = React.useRef(null)
  const swipe = onSwipeClose ? {
    onPointerDown: event => { if (event.pointerType !== "mouse") start.current = { x: event.clientX, y: event.clientY, id: event.pointerId } },
    onPointerUp: event => {
      const from = start.current
      start.current = null
      if (!from || from.id !== event.pointerId) return
      const dx = event.clientX - from.x, dy = event.clientY - from.y
      const away = { left: -dx, right: dx, top: -dy, bottom: dy }[side]
      const along = side === "left" || side === "right" ? Math.abs(dy) : Math.abs(dx)
      if (away >= SWIPE_CLOSE_PX && away > along) onSwipeClose()
    },
    onPointerCancel: () => { start.current = null }
  } : null
  return (
    <SheetPortal container={container}>
      <SheetOverlay scrim={scrim} animated={animated} style={overlayStyle} />
      <SheetPrimitive.Content
        data-slot="sheet-content"
        className={cn(
          "fixed z-50 flex flex-col gap-4 bg-background shadow-lg",
          animated && "transition ease-in-out data-[state=closed]:animate-out data-[state=closed]:duration-300 data-[state=open]:animate-in data-[state=open]:duration-500",
          side === "right" && "inset-y-0 right-0 h-full w-3/4 max-w-xs border-l",
          side === "right" && animated && "data-[state=closed]:slide-out-to-right data-[state=open]:slide-in-from-right",
          side === "left" && "inset-y-0 left-0 h-full w-3/4 max-w-xs border-r",
          side === "left" && animated && "data-[state=closed]:slide-out-to-left data-[state=open]:slide-in-from-left",
          side === "top" && "inset-x-0 top-0 h-auto border-b",
          side === "top" && animated && "data-[state=closed]:slide-out-to-top data-[state=open]:slide-in-from-top",
          side === "bottom" && "inset-x-0 bottom-0 h-auto border-t",
          side === "bottom" && animated && "data-[state=closed]:slide-out-to-bottom data-[state=open]:slide-in-from-bottom",
          className
        )}
        {...swipe}
        {...props}
      >
        {children}
        {showCloseButton && (
          <SheetPrimitive.Close className="absolute top-4 right-4 rounded-xs opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:ring-2 focus:ring-ring focus:ring-offset-2 focus:outline-hidden disabled:pointer-events-none data-[state=open]:bg-secondary">
            <XIcon className="size-4" />
            <span className="sr-only">{closeLabel}</span>
          </SheetPrimitive.Close>
        )}
      </SheetPrimitive.Content>
    </SheetPortal>
  )
}

function SheetHeader({ className, ...props }) {
  return <div data-slot="sheet-header" className={cn("flex flex-col gap-1.5 p-4", className)} {...props} />
}

function SheetFooter({ className, ...props }) {
  return <div data-slot="sheet-footer" className={cn("mt-auto flex flex-col gap-2 p-4", className)} {...props} />
}

/** @param {React.ComponentProps<typeof SheetPrimitive.Title>} props */
function SheetTitle({ className, ...props }) {
  return <SheetPrimitive.Title data-slot="sheet-title" className={cn("font-semibold text-foreground", className)} {...props} />
}

/** @param {React.ComponentProps<typeof SheetPrimitive.Description>} props */
function SheetDescription({ className, ...props }) {
  return <SheetPrimitive.Description data-slot="sheet-description" className={cn("text-ui text-muted-foreground", className)} {...props} />
}

export { Sheet, SheetTrigger, SheetClose, SheetContent, SheetHeader, SheetFooter, SheetTitle, SheetDescription }
