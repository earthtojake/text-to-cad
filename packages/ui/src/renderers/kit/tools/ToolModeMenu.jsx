import { SlidersHorizontal } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger
} from "@text-to-cad/ui/primitives/dropdown-menu";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { NAVBAR_CONTROL_CLASS } from "../../../lib/navbarRow.js";
import { TOOL_PANEL_BUTTON_CLASS } from "./ToolPanel.jsx";

/**
 * A tool's exclusive modes, as one small button — in its panel's header row beside the fold
 * chevron or the X, or (`navbar`) at the navbar's right end with the view's controls — and their
 * size: a sliders icon (the strip's button shows the mode in hand). A press opens an ordinary
 * dropdown of the modes, each its glyph and its name, then whatever options follow them
 * (`children`). Choosing a mode closes it. A tool never opens a menu from the strip, and its modes
 * are never a panel of their own.
 *
 * @param {{ label: string, modes: { id: string, label: string, icon: import("react").ReactNode }[],
 *   value: string, onChange(id: string): void, disabled?: boolean, navbar?: boolean, children?: import("react").ReactNode }} props
 *   `label` names the button and its menu ("Select mode"); the button adds the mode in hand.
 */
export default function ToolModeMenu({ label, modes, value, onChange, disabled = false, navbar = false, children = null }) {
  const current = modes.find(mode => mode.id === value) || modes[0];
  return <ToolSettingsMenu label={label} triggerLabel={`${label}: ${current.label}`} disabled={disabled} navbar={navbar}
    triggerProps={{ "data-tool-mode-trigger": current.id }}>
    <DropdownMenuRadioGroup value={current.id} onValueChange={onChange}>
      {modes.map(mode => <DropdownMenuRadioItem key={mode.id} value={mode.id} data-tool-mode={mode.id}>
        {mode.icon}{mode.label}
      </DropdownMenuRadioItem>)}
    </DropdownMenuRadioGroup>
    {children ? <><DropdownMenuSeparator />{children}</> : null}
  </ToolSettingsMenu>;
}

/**
 * A tool's settings: the small sliders button and the ordinary dropdown it opens with whatever the
 * tool offers (`children`: its items, submenus and checkboxes). In a panel's heading it sits beside
 * the fold chevron or the X; at the navbar's right end (`navbar`) it is one of the view's controls,
 * their size, named on hover, its dropdown opening down from it as Display's does.
 * `ToolModeMenu` is this with a tool's exclusive modes in it.
 *
 * @param {{ label: string, triggerLabel?: string, disabled?: boolean, navbar?: boolean, triggerProps?: object,
 *   children: import("react").ReactNode }} props
 */
export function ToolSettingsMenu({ label, triggerLabel = label, disabled = false, navbar = false, triggerProps = null, children }) {
  const trigger = <DropdownMenuTrigger asChild>
    {navbar
      ? <Button type="button" variant="ghost" size="icon-xs" aria-label={triggerLabel} disabled={disabled} {...triggerProps}
        className={cn(NAVBAR_CONTROL_CLASS, "aria-expanded:bg-accent aria-expanded:text-accent-foreground")}>
        <SlidersHorizontal className="size-3.5" aria-hidden="true" />
      </Button>
      : <button type="button" aria-label={triggerLabel} disabled={disabled} {...triggerProps}
        className={cn(TOOL_PANEL_BUTTON_CLASS, "disabled:pointer-events-none disabled:opacity-50 aria-expanded:bg-accent aria-expanded:text-foreground")}>
        <SlidersHorizontal className="size-3" aria-hidden="true" />
      </button>}
  </DropdownMenuTrigger>;
  return <DropdownMenu modal={false}>
    {navbar ? <TooltipHint content={label}>{trigger}</TooltipHint> : trigger}
    {/* Closes with no exit animation, so a quick second press always reaches the button. */}
    <DropdownMenuContent align="end" sideOffset={navbar ? 6 : 4} collisionPadding={8} aria-label={label}
      className={cn(FLOATING_SURFACE_CLASS, "w-40 data-[state=closed]:animate-none!")}>
      {children}
    </DropdownMenuContent>
  </DropdownMenu>;
}
