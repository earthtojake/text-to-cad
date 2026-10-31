"use client"

import * as React from "react"
import { AlertDialog as AlertDialogPrimitive } from "radix-ui"

import { cn } from "@text-to-cad/ui/utils"
import { buttonVariants } from "@text-to-cad/ui/primitives/button"

// shadcn's AlertDialog as shipped, on the viewer's type scale (`text-ui`) and with no window
// breakpoints (settings-ui.md): one centred card, never wider than the window less 1rem a side.

/** @param {React.ComponentProps<typeof AlertDialogPrimitive.Root>} props */
function AlertDialog({
  ...props
}) {
  return <AlertDialogPrimitive.Root data-slot="alert-dialog" {...props} />
}

/** @param {React.ComponentProps<typeof AlertDialogPrimitive.Trigger>} props */
function AlertDialogTrigger({
  ...props
}) {
  return <AlertDialogPrimitive.Trigger data-slot="alert-dialog-trigger" {...props} />
}

/** @param {React.ComponentProps<typeof AlertDialogPrimitive.Portal>} props */
function AlertDialogPortal({
  ...props
}) {
  return <AlertDialogPrimitive.Portal data-slot="alert-dialog-portal" {...props} />
}

/** @param {React.ComponentProps<typeof AlertDialogPrimitive.Overlay>} props */
function AlertDialogOverlay({
  className,
  ...props
}) {
  return (
    <AlertDialogPrimitive.Overlay
      data-slot="alert-dialog-overlay"
      className={cn(
        "fixed inset-0 z-50 bg-black/50 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0",
        className
      )}
      {...props}
    />
  )
}

/** @param {React.ComponentProps<typeof AlertDialogPrimitive.Content>} props */
function AlertDialogContent({
  className,
  ...props
}) {
  return (
    <AlertDialogPortal>
      <AlertDialogOverlay />
      <AlertDialogPrimitive.Content
        data-slot="alert-dialog-content"
        className={cn(
          "fixed top-[50%] left-[50%] z-50 grid w-full max-w-[min(28rem,calc(100%-2rem))] translate-x-[-50%] translate-y-[-50%] gap-4 rounded-lg border bg-background p-6 text-ui shadow-lg duration-200 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95",
          className
        )}
        {...props}
      />
    </AlertDialogPortal>
  )
}

/** @param {React.ComponentProps<"div">} props */
function AlertDialogHeader({
  className,
  ...props
}) {
  return <div data-slot="alert-dialog-header" className={cn("flex flex-col gap-2 text-left", className)} {...props} />
}

/** @param {React.ComponentProps<"div">} props */
function AlertDialogFooter({
  className,
  ...props
}) {
  return <div data-slot="alert-dialog-footer" className={cn("flex flex-row justify-end gap-2", className)} {...props} />
}

/** @param {React.ComponentProps<typeof AlertDialogPrimitive.Title>} props */
function AlertDialogTitle({
  className,
  ...props
}) {
  return <AlertDialogPrimitive.Title data-slot="alert-dialog-title" className={cn("text-ui font-semibold", className)} {...props} />
}

/** @param {React.ComponentProps<typeof AlertDialogPrimitive.Description>} props */
function AlertDialogDescription({
  className,
  ...props
}) {
  return <AlertDialogPrimitive.Description data-slot="alert-dialog-description" className={cn("text-ui text-muted-foreground", className)} {...props} />
}

/** @param {React.ComponentProps<typeof AlertDialogPrimitive.Action> & { variant?: "default" | "destructive" | "outline" | "secondary" | "ghost" | "link" }} props */
function AlertDialogAction({
  className,
  variant = "default",
  ...props
}) {
  return <AlertDialogPrimitive.Action className={cn(buttonVariants({ variant, size: "sm" }), className)} {...props} />
}

/** @param {React.ComponentProps<typeof AlertDialogPrimitive.Cancel>} props */
function AlertDialogCancel({
  className,
  ...props
}) {
  return <AlertDialogPrimitive.Cancel className={cn(buttonVariants({ variant: "outline", size: "sm" }), className)} {...props} />
}

export {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogOverlay,
  AlertDialogPortal,
  AlertDialogTitle,
  AlertDialogTrigger,
}
