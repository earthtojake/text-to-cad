import { FieldLabel } from "@cad/ui/primitives/field-label";
import { Switch } from "@cad/ui/primitives/switch";
import { VALUE_DROPDOWN_TRIGGER_CLASS, ValueDropdown } from "@cad/ui/primitives/value-dropdown";
import { cn } from "@cad/ui/utils";

// The view's panel's two settings rows, ONE each, so every control of a kind looks alike wherever it stands (Joints'
// Position, Animation's Clip, Speed and Loop, a board's Others and Pours; `docs/viewer-ux.md`, "The panel"). Both are
// 28px on the panel's one inset: the label (muted, `FieldLabel`) on its inset (`--panel-inset`, the
// body's padding: a row pads nothing), the control ending on its right inset, a dropdown half the row wide (wider only
// where its value needs it).

/** A settings row's dropdown trigger, the value dropdown's own: bordered, 6rem at least, its value the foreground (in a
 * `PanelSelectRow`, half the row wide). */
export const PANEL_DROPDOWN_CLASS = VALUE_DROPDOWN_TRIGGER_CLASS;

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
  return <div className={cn("grid h-control min-w-0 items-center gap-2", bare ? "grid-cols-1" : "grid-cols-[minmax(max-content,1fr)_minmax(50%,max-content)]", className)} data-panel-select-row="" {...rowProps}>
    {bare ? null : <FieldLabel className="leading-(--cad-leading-xs)" {...labelProps}>{label}</FieldLabel>}
    <ValueDropdown value={value} options={options} onChange={onChange} disabled={disabled} fallback={fallback} label={label}
      className="w-full justify-self-stretch"
      triggerProps={{ "aria-label": triggerLabel || `${label}: ${shown}`, title: bare ? label : undefined, "data-panel-dropdown": "", ...triggerProps }}
      optionProps={optionProps} />
  </div>;
}

/**
 * A setting that is on or off: its icon and its label, the switch at the row's right end. The whole row is the
 * switch's label, so a press anywhere on it turns it.
 * @param {{ label: string, Icon?: Function | null, checked: boolean, onChange(checked: boolean): void, disabled?: boolean,
 *   className?: string, rowProps?: object, switchProps?: object }} props
 */
export function PanelSwitchRow({ label, Icon = null, checked, onChange, disabled = false, className, rowProps = null, switchProps = null }) {
  return <label className={cn("flex h-control min-w-0 items-center gap-2", disabled ? "cursor-not-allowed" : "cursor-default", className)}
    data-panel-switch-row="" data-value={checked ? "on" : "off"} {...rowProps}>
    {Icon ? <Icon className="size-4 shrink-0 text-muted-foreground" aria-hidden="true" /> : null}
    <FieldLabel className="flex-1 leading-(--cad-leading-xs)">{label}</FieldLabel>
    <Switch checked={checked} disabled={disabled} aria-label={label} onCheckedChange={next => onChange(next === true)} {...switchProps} />
  </label>;
}
