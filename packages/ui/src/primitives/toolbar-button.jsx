import { Button } from "@hardcore/ui/primitives/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@hardcore/ui/primitives/tooltip";
import { cn } from "@hardcore/ui/utils";

// The icon button every floating toolbar is made of: the CAD interaction tools,
// the drawing tools under them, and the standalone drawing editor's toolbar.
export const TOOLBAR_ICON_BUTTON_CLASS = "size-6 rounded-sm text-sidebar-foreground/70 shadow-none transition hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-ring/45 data-[variant=secondary]:bg-sidebar-accent data-[variant=secondary]:text-sidebar-accent-foreground data-[variant=secondary]:hover:bg-sidebar-accent";

/**
 * `tooltip={false}` leaves the accessible name and shows nothing on hover: for a
 * toolbar over a canvas, where a tooltip would cover what is being pointed at.
 * @param {{ label: string, active?: boolean, tooltip?: boolean, tooltipSide?: "top" | "right" | "bottom" | "left", className?: string,
 *   children?: import("react").ReactNode } & import("react").ButtonHTMLAttributes<HTMLButtonElement>} props
 */
export function ToolbarButton({
  label,
  active = false,
  tooltip = true,
  tooltipSide = "bottom",
  className,
  children,
  ...props
}) {
  const button = (
    <Button
      type="button"
      variant={active ? "secondary" : "ghost"}
      size="icon-xs"
      className={cn(TOOLBAR_ICON_BUTTON_CLASS, className)}
      aria-label={label}
      {...props}
    >
      {children}
    </Button>
  );
  if (!tooltip) return button;
  return (
    <Tooltip>
      <TooltipTrigger asChild>{button}</TooltipTrigger>
      <TooltipContent side={tooltipSide} sideOffset={6}>
        {label}
      </TooltipContent>
    </Tooltip>
  );
}
