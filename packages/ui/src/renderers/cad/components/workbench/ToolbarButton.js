import { Button } from "@hardcore/ui/primitives/button";
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger
} from "@hardcore/ui/primitives/tooltip";
import { cn } from "@hardcore/ui/utils";

export function ToolbarButton({
  label,
  active = false,
  tooltipSide = "bottom",
  className,
  children,
  ...props
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant={active ? "secondary" : "ghost"}
          size="icon-xs"
          className={cn(
            "size-6 rounded-sm text-sidebar-foreground/70 shadow-none transition hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-ring/45 data-[variant=secondary]:bg-sidebar-accent data-[variant=secondary]:text-sidebar-accent-foreground data-[variant=secondary]:hover:bg-sidebar-accent",
            className
          )}
          aria-label={label}
          {...props}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side={tooltipSide} sideOffset={6}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}

export function ToolbarTextButton({
  label,
  active = false,
  tooltipSide = "top",
  className,
  children,
  ...props
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <Button
          type="button"
          variant={active ? "secondary" : "ghost"}
          size="sm"
          className={cn(
            "min-h-9 flex-1 touch-manipulation px-3 text-xs shadow-none",
            className
          )}
          aria-label={label}
          {...props}
        >
          {children}
        </Button>
      </TooltipTrigger>
      <TooltipContent side={tooltipSide} sideOffset={6}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}
