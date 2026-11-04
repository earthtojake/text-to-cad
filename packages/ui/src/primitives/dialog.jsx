"use client"

import * as React from "react"
import { Dialog as DialogPrimitive } from "radix-ui"

import { cn } from "@cad/ui/utils"

// shadcn's Dialog as shipped, as `alert-dialog.jsx` is: on the viewer's type scale (`text-ui`) and with
// no window breakpoints (settings-ui.md): one centred card, never wider than the window less 1rem a side.
// Its corner X is left out: the viewer's dialogs close by their own buttons, Escape or a press outside.

/** @param {React.ComponentProps<typeof DialogPrimitive.Root>} props */
function Dialog({
  ...props
}) {
  return <DialogPrimitive.Root data-slot="dialog" {...props} />
}

/** @param {React.ComponentProps<typeof DialogPrimitive.Trigger>} props */
function DialogTrigger({
  ...props
}) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />
}

/** @param {React.ComponentProps<typeof DialogPrimitive.Portal>} props */
function DialogPortal({
  ...props
}) {
  return <DialogPrimitive.Portal data-slot="dialog-portal" {...props} />
}

/** @param {React.ComponentProps<typeof DialogPrimitive.Close>} props */
function DialogClose({
  ...props
}) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />
}

/** @param {React.ComponentProps<typeof DialogPrimitive.Overlay>} props */
function DialogOverlay({
  className,
  ...props
}) {
  return (
    <DialogPrimitive.Overlay
      data-slot="dialog-overlay"
      className={cn(
        "fixed inset-0 z-50 bg-black/50 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0",
        className
      )}
      {...props}
    />
  )
}

/** @param {React.ComponentProps<typeof DialogPrimitive.Content>} props */
function DialogContent({
  className,
  children,
  ...props
}) {
  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Content
        data-slot="dialog-content"
        className={cn(
          "fixed top-[50%] left-[50%] z-50 grid w-full max-w-[min(28rem,calc(100%-2rem))] translate-x-[-50%] translate-y-[-50%] gap-4 rounded-lg border bg-background p-6 text-ui shadow-lg duration-200 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
          className
        )}
        {...props}
      >
        {children}
      </DialogPrimitive.Content>
    </DialogPortal>
  )
}

/** @param {React.ComponentProps<"div">} props */
function DialogHeader({
  className,
  ...props
}) {
  return <div data-slot="dialog-header" className={cn("flex flex-col gap-2 text-left", className)} {...props} />
}

/** @param {React.ComponentProps<"div">} props */
function DialogFooter({
  className,
  ...props
}) {
  return <div data-slot="dialog-footer" className={cn("flex flex-row justify-end gap-2", className)} {...props} />
}

/** @param {React.ComponentProps<typeof DialogPrimitive.Title>} props */
function DialogTitle({
  className,
  ...props
}) {
  return <DialogPrimitive.Title data-slot="dialog-title" className={cn("text-ui leading-none font-semibold", className)} {...props} />
}

/** @param {React.ComponentProps<typeof DialogPrimitive.Description>} props */
function DialogDescription({
  className,
  ...props
}) {
  return <DialogPrimitive.Description data-slot="dialog-description" className={cn("text-ui text-muted-foreground", className)} {...props} />
}

export {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogOverlay,
  DialogPortal,
  DialogTitle,
  DialogTrigger,
}
