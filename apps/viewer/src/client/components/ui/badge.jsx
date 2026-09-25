import * as React from "react"
import { cva } from "class-variance-authority";

import { cn } from "@/ui/utils"

const badgeVariants = cva(
  "inline-flex w-fit shrink-0 items-center justify-center gap-1 overflow-hidden rounded-md border px-2 py-0.5 text-xs whitespace-nowrap transition-colors [&>svg]:size-3",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        destructive:
          "border-transparent bg-destructive text-white dark:bg-destructive/60",
        "destructive-outline":
          "border-destructive/45 bg-destructive/10 text-destructive dark:border-red-400/40 dark:text-red-300",
        outline: "text-foreground",
        warning: "border-amber-500/45 bg-amber-500/10 text-amber-800 dark:text-amber-300",
        "warning-outline":
          "border-amber-500/45 bg-amber-500/10 text-amber-800 dark:text-amber-300",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
)

function Badge({
  className,
  variant,
  ...props
}) {
  return (
    <span
      data-slot="badge"
      className={cn(badgeVariants({ variant }), className)}
      {...props} />
  );
}

export { Badge, badgeVariants }
