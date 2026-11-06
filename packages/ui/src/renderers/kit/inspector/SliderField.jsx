import { Slider } from "@cad/ui/primitives/slider";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { cn } from "@cad/ui/utils";
import { FileSheetValueInput } from "./FileSheet.js";

// The value's width: as wide as its text and one figure more, so a unit is never cut and a figure
// typed in has room; tabular figures, so it does not twitch while the slider moves.
const valueWidth = text => ({ width: `calc(${Math.max(2, String(text ?? "").length) + 1}ch + 0.5rem)` });

/**
 * THE control for a number a slider sets (`docs/settings-ui.md`, "The slider control"): every one
 * in the viewer is this, and nothing else draws the slider primitive but the playbar's scrubber.
 *
 * In a panel (the default) it is two lines, shadcn's: the label at the left and the value at the
 * right, then the slider the control's full width, from the label's left edge to the value's right
 * edge. `inline`: a toolbar row's, one line: the label (the tool's own button or name), the slider,
 * the value. The value is an editable number (Enter or blur commits a changed one, Escape cancels) with no box in
 * any state: plain right-aligned text, a soft fill under the pointer or the keyboard.
 *
 * @param {{
 *   label: import("react").ReactNode, labelTitle?: string, name: string,
 *   value: number, min: number, max: number, step?: number, origin?: number,
 *   onValueChange(value: number): void, onValueCommit?(value: number): void,
 *   text: string, onTextCommit(draft: string): void, textLabel: string,
 *   hint?: import("react").ReactNode, disabled?: boolean, inline?: boolean, className?: string,
 *   thumbProps?: object,
 * }} props `name` is the slider's accessible name, `textLabel` the value's; `hint` a tooltip on the
 *   slider (a joint's range). Other props (`data-*`) go on the control's root.
 */
export function SliderField({
  label, labelTitle, name, value, min, max, step = 1, origin, onValueChange, onValueCommit,
  text, onTextCommit, textLabel, hint = null, disabled = false, inline = false, className, thumbProps, ...props
}) {
  const slider = <Slider data-slider-field-track="" className={inline ? "h-6 min-w-0 flex-1 px-2" : "h-3 min-w-0"}
    value={[Number(value) || 0]} min={min} max={max} step={step} origin={origin} disabled={disabled}
    thumbProps={{ "aria-label": name, ...thumbProps }}
    onValueChange={next => onValueChange?.(next?.[0] ?? value)}
    onValueCommit={onValueCommit ? next => onValueCommit(next?.[0] ?? value) : undefined} />;
  // A value left as it shows commits nothing: a tab through it or a click on it must not write the
  // rounded text back over the value it rounds (123.4° as 123).
  const commitText = draft => { if (String(draft ?? "").trim() !== String(text ?? "").trim()) onTextCommit?.(draft); };
  const field = <FileSheetValueInput quiet value={text} onValueCommit={commitText} disabled={disabled} ariaLabel={textLabel}
    className={inline ? "h-6" : "-my-0.5 -mr-1 h-5"} style={valueWidth(text)} data-slider-field-value="" />;
  if (inline) {
    return <div data-slider-field="" data-inline="" className={cn("flex min-w-0 flex-1 items-center gap-1", className)} {...props}>
      {label}
      {hint ? <TooltipHint content={hint}>{slider}</TooltipHint> : slider}
      {field}
    </div>;
  }
  return <div data-slider-field="" className={cn("min-w-0 px-2 py-1", className)} {...props}>
    <div className="flex h-4 min-w-0 items-center justify-between gap-2">
      <TooltipHint content={labelTitle || label} overflowOnly><span data-slider-field-label=""
        className={cn("block min-w-0 truncate text-tiny leading-4 text-foreground", disabled && "opacity-50")}>{label}</span></TooltipHint>
      {field}
    </div>
    {hint ? <TooltipHint content={hint}>{slider}</TooltipHint> : slider}
  </div>;
}
