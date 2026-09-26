import { Button } from "@hardcore/ui/primitives/button";
import { cn } from "@hardcore/ui/utils";

export { TOOLBAR_ICON_BUTTON_CLASS, ToolbarButton } from "@hardcore/ui/primitives/toolbar-button";

export function ToolbarTextButton({
  label,
  active = false,
  tooltipSide = "top",
  className,
  children,
  ...props
}) {
  return (
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
  );
}
