import { createContext, useContext } from "react";
import { Button } from "@cad/ui/primitives/button";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { cn } from "@cad/ui/utils";

// The icon button every floating toolbar is made of: the CAD interaction tools,
// the annotation tools under them.
// Its fills are the toolbar's own in both themes, never the base Button's ghost hover (whose `dark:hover:bg-accent/50`
// outranks a plain `hover:` and was all but invisible on a dark surface). In the dark they are the foreground laid
// over whatever the surface shows (10% under the pointer, 16% pressed), so they read on the floating surface over a
// dark canvas and over a light viewport alike, where the opaque #444 matched the surface it stood on.
export const TOOLBAR_ICON_BUTTON_CLASS = ["size-icon-button rounded-sm text-sidebar-foreground/70 shadow-none transition hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:ring-2 focus-visible:ring-ring/45",
  "data-[variant=secondary]:bg-sidebar-accent data-[variant=secondary]:text-sidebar-accent-foreground data-[variant=secondary]:hover:bg-sidebar-accent data-[variant=secondary]:[&>svg]:text-brand-icon",
  "dark:hover:bg-foreground/10 dark:data-[variant=secondary]:bg-foreground/16 dark:data-[variant=secondary]:hover:bg-foreground/16"].join(" ");

const ToolbarTooltipVisibility = createContext(true);
// Portalled tips must follow chrome visibility, rather than remaining above an
// inert/faded toolbar. The trigger DOM stays mounted for menu focus restoration.
export function ToolbarTooltipScope({ enabled = true, children }) {
  return <ToolbarTooltipVisibility.Provider value={enabled}>{children}</ToolbarTooltipVisibility.Provider>;
}

/**
 * `tooltip={false}` leaves the accessible name and shows nothing on hover: for a
 * toolbar over a canvas, where a tooltip would cover what is being pointed at. A string is the
 * tooltip's text where it is shorter than the accessible name (Display's "Display"). `shortcut`, the
 * key that does what the button does ("V", "⇧L"), follows the name in the tooltip, muted, as a
 * design tool's tooltips show it, and is the button's `aria-keyshortcuts`. `active`: the tool in hand,
 * in the strip's pressed fill (neutral), its icon in the brand's icon colour (`--brand-icon`), with no tooltip (it is chosen already).
 * An expanded button (`aria-expanded`, a menu's trigger with its menu open) has no tooltip either, unless what it expands
 * is not over it (`expandedTooltip`: the navbar's panel toggle, whose panel opens beside the model). `tooltipHidden`
 * closes its tooltip and keeps it closed (the panel toggle's while its panel peeks: the tip has done its job).
 * @param {{ label: string, active?: boolean, tooltip?: boolean | string, tooltipSide?: "top" | "right" | "bottom" | "left",
 *   className?: string, shortcut?: string, children?: import("react").ReactNode } & import("react").ButtonHTMLAttributes<HTMLButtonElement>} props
 */
export function ToolbarButton({
  label,
  active = false,
  tooltip = true,
  tooltipSide = "bottom",
  shortcut = "",
  expandedTooltip = false,
  tooltipHidden = false,
  className,
  children,
  ...props
}) {
  const tipsVisible = useContext(ToolbarTooltipVisibility);
  const tipEnabled = tipsVisible && tooltip && !tooltipHidden && !active && !props.disabled && (expandedTooltip || props["aria-expanded"] !== true);
  const button = (
    <Button
      type="button"
      variant={active ? "secondary" : "ghost"}
      size="icon-xs"
      className={cn(TOOLBAR_ICON_BUTTON_CLASS, className)}
      aria-label={label}
      aria-keyshortcuts={shortcut ? shortcut.replace(/^⇧/, "Shift+") : undefined}
      {...props}
    >
      {children}
    </Button>
  );
  if (!tooltip) return button;
  const text = typeof tooltip === "string" ? tooltip : label;
  const content = shortcut ? <span className="flex items-center gap-3">{text}<span className="text-muted-foreground" data-tooltip-shortcut="">{shortcut}</span></span> : text;
  return <TooltipHint content={content} disabled={!tipEnabled} side={tooltipSide}>{button}</TooltipHint>;
}
