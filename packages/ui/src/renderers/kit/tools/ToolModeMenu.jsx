import { SlidersHorizontal } from "lucide-react";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger
} from "@hardcore/ui/primitives/dropdown-menu";
import { cn } from "@hardcore/ui/utils";
import { FLOATING_SURFACE_CLASS } from "./floatingSurface.js";
import { TOOL_PANEL_BUTTON_CLASS } from "./ToolPanel.jsx";

/**
 * A tool's exclusive modes, as one small button in its panel's header row beside the fold
 * chevron or the X, and their size: a sliders icon (the strip's button shows the mode in hand).
 * A press opens an ordinary dropdown of the modes, each its glyph and its name, then whatever
 * options follow them (`children`). Choosing a mode closes
 * it. A tool never opens a menu from the strip, and its modes are never a panel of their own.
 *
 * @param {{ label: string, modes: { id: string, label: string, icon: import("react").ReactNode }[],
 *   value: string, onChange(id: string): void, disabled?: boolean, children?: import("react").ReactNode }} props
 *   `label` names the button and its menu ("Select mode"); the button adds the mode in hand.
 */
export default function ToolModeMenu({ label, modes, value, onChange, disabled = false, children = null }) {
  const current = modes.find(mode => mode.id === value) || modes[0];
  return <ToolSettingsMenu label={label} triggerLabel={`${label}: ${current.label}`} disabled={disabled} triggerProps={{ "data-tool-mode-trigger": current.id }}>
    <DropdownMenuRadioGroup value={current.id} onValueChange={onChange}>
      {modes.map(mode => <DropdownMenuRadioItem key={mode.id} value={mode.id} data-tool-mode={mode.id}>
        {mode.icon}{mode.label}
      </DropdownMenuRadioItem>)}
    </DropdownMenuRadioGroup>
    {children ? <><DropdownMenuSeparator />{children}</> : null}
  </ToolSettingsMenu>;
}

/**
 * A panel heading's settings: the small sliders button, beside the fold chevron or the X, and the
 * ordinary dropdown it opens with whatever the tool offers (`children`: its items, submenus and
 * checkboxes). `ToolModeMenu` is this with a tool's exclusive modes in it.
 *
 * @param {{ label: string, triggerLabel?: string, disabled?: boolean, triggerProps?: object, children: import("react").ReactNode }} props
 */
export function ToolSettingsMenu({ label, triggerLabel = label, disabled = false, triggerProps = null, children }) {
  return <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild>
      <button type="button" aria-label={triggerLabel} disabled={disabled} {...triggerProps}
        className={cn(TOOL_PANEL_BUTTON_CLASS, "disabled:pointer-events-none disabled:opacity-50 aria-expanded:bg-accent aria-expanded:text-foreground")}>
        <SlidersHorizontal className="size-3" aria-hidden="true" />
      </button>
    </DropdownMenuTrigger>
    {/* Closes with no exit animation, so a quick second press always reaches the button. */}
    <DropdownMenuContent align="end" sideOffset={4} collisionPadding={8} aria-label={label}
      className={cn(FLOATING_SURFACE_CLASS, "w-40 data-[state=closed]:animate-none!")}>
      {children}
    </DropdownMenuContent>
  </DropdownMenu>;
}
