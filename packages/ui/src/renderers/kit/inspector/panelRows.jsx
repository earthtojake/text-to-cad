import { ChevronDown } from "lucide-react";
import { FieldLabel } from "@cad/ui/primitives/field-label";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger
} from "@cad/ui/primitives/dropdown-menu";
import { Switch } from "@cad/ui/primitives/switch";
import { cn } from "@cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";

// The right panel's two settings rows, ONE each, so every control of a kind looks alike wherever it stands (View's
// Display and Grid, Joints' Position, Animation's Clip, Speed, Loop and Autoplay; `docs/settings-ui.md`, "The two
// panels"). Both are 28px on the panel's lines: the label (muted, `FieldLabel`) on its inset (`--panel-inset`, the
// body's padding: a row pads nothing), the control ending on its right inset.

/** A settings row's dropdown, Joints' Position's: bordered, as wide as its value (6rem at least), its value the foreground. */
export const PANEL_DROPDOWN_CLASS = "flex h-7 min-w-24 max-w-full items-center justify-between gap-1.5 justify-self-end rounded-md border border-input bg-transparent px-2 "
  + "text-left text-ui shadow-xs outline-none focus-visible:ring-2 focus-visible:ring-ring/45 aria-expanded:bg-accent disabled:cursor-not-allowed disabled:opacity-50 "
  + "dark:bg-input/30 dark:hover:bg-input/50";

/**
 * A label and a bordered dropdown of its choices: the one in hand shown (its icon, where it has one, and its name),
 * its menu every choice with its icon, the one in hand checked.
 * @param {{ label: string, value: string, options: readonly { value: string, label: string, Icon?: Function, disabled?: boolean }[],
 *   onChange(value: string): void, disabled?: boolean, fallback?: string, triggerLabel?: string, className?: string,
 *   rowProps?: object, labelProps?: object, triggerProps?: object, optionProps?(option: object): object }} props
 *   `fallback`: what the trigger shows where no choice is the value ("Custom"). `triggerLabel`: its accessible name.
 *   `bare`: no label drawn, the dropdown the row's full width, `label`
 *   its tooltip and its menu's name.
 */
export function PanelSelectRow({ label, value, options, onChange, disabled = false, fallback = "", triggerLabel, className, rowProps = null,
  labelProps = null, triggerProps = null, optionProps = null, bare = false }) {
  const active = options.find(option => option.value === value) || null;
  const shown = active?.label ?? fallback;
  const Icon = active?.Icon || null;
  return <div className={cn("grid h-7 min-w-0 items-center gap-2", bare ? "grid-cols-1" : "grid-cols-[4rem_minmax(0,1fr)]", className)} data-panel-select-row="" {...rowProps}>
    {bare ? null : <FieldLabel className="leading-4" {...labelProps}>{label}</FieldLabel>}
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild disabled={disabled}>
        <button type="button" disabled={disabled} aria-label={triggerLabel || `${label}: ${shown}`} title={bare ? label : undefined}
          className={cn(PANEL_DROPDOWN_CLASS, bare && "w-full justify-self-stretch")} data-panel-dropdown="" {...triggerProps}>
          {Icon ? <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" /> : null}
          <span className="min-w-0 flex-1 truncate text-foreground" data-field-value="">{shown}</span>
          <ChevronDown className="size-3 shrink-0 opacity-60" aria-hidden="true" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" sideOffset={4} collisionPadding={8} aria-label={label}
        className={cn(FLOATING_SURFACE_CLASS, "min-w-(--radix-dropdown-menu-trigger-width) data-[state=closed]:animate-none!")}>
        <DropdownMenuRadioGroup value={active ? String(active.value) : ""} onValueChange={next => {
          const option = options.find(entry => String(entry.value) === next);
          if (option && option.value !== value) onChange(option.value);
        }}>
          {options.map(option => <DropdownMenuRadioItem key={String(option.value)} value={String(option.value)} disabled={option.disabled === true}
            {...optionProps?.(option)}>
            {option.Icon ? <option.Icon className="size-4 text-muted-foreground" aria-hidden="true" /> : null}
            <span className="min-w-0 truncate">{option.label}</span>
          </DropdownMenuRadioItem>)}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>;
}

/**
 * A setting that is on or off: its icon and its label, the switch at the row's right end. The whole row is the
 * switch's label, so a press anywhere on it turns it.
 * @param {{ label: string, Icon?: Function | null, checked: boolean, onChange(checked: boolean): void, disabled?: boolean,
 *   className?: string, rowProps?: object, switchProps?: object }} props
 */
export function PanelSwitchRow({ label, Icon = null, checked, onChange, disabled = false, className, rowProps = null, switchProps = null }) {
  return <label className={cn("flex h-7 min-w-0 items-center gap-2", disabled ? "cursor-not-allowed" : "cursor-default", className)}
    data-panel-switch-row="" data-value={checked ? "on" : "off"} {...rowProps}>
    {Icon ? <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" /> : null}
    <FieldLabel className="flex-1 leading-4">{label}</FieldLabel>
    <Switch checked={checked} disabled={disabled} aria-label={label} onCheckedChange={next => onChange(next === true)} {...switchProps} />
  </label>;
}
