"use client"

import * as React from "react"
import { AlertDialog as AlertDialogPrimitive } from "radix-ui"

import { cn } from "@/lib/utils"
import { buttonVariants } from "@/components/ui/button"

function AlertDialog({
  ...props
}) {
  return <AlertDialogPrimitive.Root data-slot="alert-dialog" {...props} />;
}

function AlertDialogTrigger({
  ...props
}) {
  return <AlertDialogPrimitive.Trigger data-slot="alert-dialog-trigger" {...props} />;
}

function AlertDialogPortal({
  ...props
}) {
  return <AlertDialogPrimitive.Portal data-slot="alert-dialog-portal" {...props} />;
}

const AlertDialogOverlay = React.forwardRef(function AlertDialogOverlay({
  className,
  ...props
}, ref) {
  return (
    <AlertDialogPrimitive.Overlay
      ref={ref}
      data-slot="alert-dialog-overlay"
      className={cn(
        "fixed inset-0 z-50 bg-black/50 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:animate-in data-[state=open]:fade-in-0",
        className
      )}
      {...props} />
  );
})

const AlertDialogContent = React.forwardRef(function AlertDialogContent({
  className,
  ...props
}, ref) {
  return (
    <AlertDialogPortal>
      <AlertDialogOverlay />
      <AlertDialogPrimitive.Content
        ref={ref}
        data-slot="alert-dialog-content"
        className={cn(
          "cad-glass-popover fixed top-[50%] left-[50%] z-50 grid w-full max-w-[calc(100%-2rem)] translate-x-[-50%] translate-y-[-50%] gap-4 rounded-md border p-6 text-foreground shadow-lg duration-200 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:zoom-out-95 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:zoom-in-95 sm:max-w-lg",
          className
        )}
        {...props} />
    </AlertDialogPortal>
  );
})

function AlertDialogHeader({
  className,
  ...props
}) {
  return (
    <div
      data-slot="alert-dialog-header"
      className={cn("flex flex-col gap-2 text-center sm:text-left", className)}
      {...props} />
  );
}

function AlertDialogFooter({
  className,
  ...props
}) {
  return (
    <div
      data-slot="alert-dialog-footer"
      className={cn("flex flex-col-reverse gap-2 sm:flex-row sm:justify-end", className)}
      {...props} />
  );
}

const AlertDialogTitle = React.forwardRef(function AlertDialogTitle({
  className,
  ...props
}, ref) {
  return (
    <AlertDialogPrimitive.Title
      ref={ref}
      data-slot="alert-dialog-title"
      className={cn("text-lg font-semibold", className)}
      {...props} />
  );
})

const AlertDialogDescription = React.forwardRef(function AlertDialogDescription({
  className,
  ...props
}, ref) {
  return (
    <AlertDialogPrimitive.Description
      ref={ref}
      data-slot="alert-dialog-description"
      className={cn("text-sm text-muted-foreground", className)}
      {...props} />
  );
})

const AlertDialogAction = React.forwardRef(function AlertDialogAction({
  className,
  ...props
}, ref) {
  return (
    <AlertDialogPrimitive.Action
      ref={ref}
      className={cn(buttonVariants(), className)}
      {...props} />
  );
})

const AlertDialogCancel = React.forwardRef(function AlertDialogCancel({
  className,
  ...props
}, ref) {
  return (
    <AlertDialogPrimitive.Cancel
      ref={ref}
      className={cn(buttonVariants({ variant: "outline" }), className)}
      {...props} />
  );
})

export {
  AlertDialog,
  AlertDialogPortal,
  AlertDialogOverlay,
  AlertDialogTrigger,
  AlertDialogContent,
  AlertDialogHeader,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogDescription,
  AlertDialogAction,
  AlertDialogCancel,
}
