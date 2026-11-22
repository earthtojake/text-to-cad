import { ChevronDown } from "lucide-react";
import { cn } from "@cad/ui/utils";
import { DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger } from "./dropdown-menu.jsx";
import { FLOATING_SURFACE_CLASS } from "../lib/floatingSurface.js";

// THE value dropdown (`docs/design-system.md`, "Dropdowns"): every place that picks one value of a list from its own trigger —
// a panel's row, a settings card's row (Display's, Preview's Settings), a board's display — is this, on the one
// `DropdownMenu` primitive: one popup, one touch rule (its trigger's: a mouse opens at the press, a finger toggles at its
// click from the state at the press), one keyboard, one look. A menu of actions stays a plain `DropdownMenu`.

/** The trigger's look: the field's border and fill, the control's height (THE scale), the value then a chevron. */
export const VALUE_DROPDOWN_TRIGGER_CLASS = "flex h-control min-w-24 max-w-full items-center justify-between gap-1.5 justify-self-end rounded-md border border-input bg-transparent px-2 "
  + "text-left text-ui shadow-xs outline-none focus-visible:ring-2 focus-visible:ring-ring/45 aria-expanded:bg-accent disabled:cursor-not-allowed disabled:opacity-50 "
  + "dark:bg-input/30 dark:hover:bg-input/50";

/**
 * @typedef {{ value: unknown, label: import("react").ReactNode, Icon?: import("react").ComponentType<any> | null, disabled?: boolean }} ValueOption
 * @param {{ value: unknown, options: readonly ValueOption[], onChange(value: unknown): void, label: string, disabled?: boolean,
 *   fallback?: import("react").ReactNode, align?: "start" | "center" | "end", fixedWidth?: boolean, iconClassName?: string,
 *   className?: string, triggerProps?: object | null, optionProps?: ((option: ValueOption) => object) | null }} props
 *   `label`: the list's accessible name, and the trigger's ("label: value") unless `triggerProps` names it. `fallback`: what
 *   the trigger says where no option is the value. `fixedWidth`: the trigger as wide as its widest option, so a card's
 *   dropdowns keep one width whatever is chosen. `optionProps(option)`: what each item carries (its data attributes).
 */
export function ValueDropdown({ value, options, onChange, label, disabled = false, fallback = "", align = "end", fixedWidth = false,
  iconClassName = "size-4", className, triggerProps = null, optionProps = null }) {
  const active = options.find(option => option.value === value) || null;
  const shown = active?.label ?? fallback;
  const face = option => <>
    {option?.Icon ? <option.Icon className={cn(iconClassName, "shrink-0 text-muted-foreground")} aria-hidden="true" /> : null}
    <span className="min-w-0 flex-1 truncate text-foreground" data-field-value={option === active ? "" : undefined}>{option ? option.label : shown}</span>
  </>;
  return <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild disabled={disabled}>
      <button type="button" disabled={disabled} aria-label={`${label}: ${typeof shown === "string" ? shown : ""}`}
        className={cn(VALUE_DROPDOWN_TRIGGER_CLASS, className)} data-value-dropdown="" {...triggerProps}>
        {fixedWidth
          // Every option laid in the one cell, the chosen one seen: the trigger is as wide as its widest.
          ? <span className="grid min-w-0 flex-1" data-value-dropdown-faces="">
            {options.map(option => <span key={String(option.value)} aria-hidden={option === active ? undefined : true}
              className={cn("col-start-1 row-start-1 flex min-w-0 items-center gap-1", option === active ? null : "invisible")}>{face(option)}</span>)}
            {active ? null : <span className="col-start-1 row-start-1 flex min-w-0 items-center gap-1">{face(null)}</span>}
          </span>
          : <span className="flex min-w-0 flex-1 items-center gap-1.5">{face(active)}</span>}
        <ChevronDown className="size-3 shrink-0 opacity-60" aria-hidden="true" />
      </button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align={align} sideOffset={4} collisionPadding={8} aria-label={label}
      className={cn(FLOATING_SURFACE_CLASS, "min-w-(--radix-dropdown-menu-trigger-width) data-[state=closed]:animate-none!")}>
      <DropdownMenuRadioGroup value={active ? String(active.value) : ""} onValueChange={next => {
        const option = options.find(entry => String(entry.value) === next);
        if (option && option.value !== value) onChange(option.value);
      }}>
        {options.map(option => <DropdownMenuRadioItem key={String(option.value)} value={String(option.value)} disabled={option.disabled === true}
          {...optionProps?.(option)}>
          {option.Icon ? <option.Icon className={cn(iconClassName, "text-muted-foreground")} aria-hidden="true" /> : null}
          <span className="min-w-0 truncate">{option.label}</span>
        </DropdownMenuRadioItem>)}
      </DropdownMenuRadioGroup>
    </DropdownMenuContent>
  </DropdownMenu>;
}
