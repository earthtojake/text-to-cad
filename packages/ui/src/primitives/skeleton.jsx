import { cn } from "@hardcore/ui/utils"

function Skeleton({
  className,
  ...props
}) {
  return (
    <div
      data-slot="skeleton"
      className={cn("animate-pulse rounded-md bg-accent", className)}
      {...props} />
  );
}

export { Skeleton }
