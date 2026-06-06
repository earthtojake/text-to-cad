import { Toast as ToastPrimitive } from "radix-ui"

import { cn } from "@/ui/utils"

function ToastProvider({
  ...props
}) {
  return <ToastPrimitive.Provider data-slot="toast-provider" {...props} />
}

function Toast({
  className,
  ...props
}) {
  return (
    <ToastPrimitive.Root
      data-slot="toast"
      className={cn(
        "cad-glass-popover pointer-events-auto rounded-md border border-border px-4 py-2.5 text-xs font-medium text-popover-foreground shadow-lg shadow-black/10 outline-none data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-right-2 data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-top-2",
        className
      )}
      {...props} />
  )
}

function ToastTitle({
  ...props
}) {
  return <ToastPrimitive.Title data-slot="toast-title" {...props} />
}

function ToastViewport({
  className,
  ...props
}) {
  return (
    <ToastPrimitive.Viewport
      data-slot="toast-viewport"
      className={cn(
        "fixed right-4 top-4 z-50 flex max-h-screen w-[min(calc(100vw-2rem),22rem)] flex-col gap-2 outline-none",
        className
      )}
      {...props} />
  )
}

export {
  Toast,
  ToastProvider,
  ToastTitle,
  ToastViewport
}
