import { useRef } from "react";
import { Slider } from "@cad/ui/primitives/slider";
import { FieldLabel } from "@cad/ui/primitives/field-label";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { cn } from "@cad/ui/utils";
import { capturePointer, releasePointer } from "../../../lib/pointerCapture.js";
import { SliderValueField } from "./SliderValueField.jsx";
import { clampNumber, decimalsOf } from "./numberText.js";

// A press on the label that moves this far sideways is a scrub, not a click (the label's hint, a tap).
const SCRUB_SLOP_PX = 3;

/**
 * THE control for a number a slider sets (`docs/design-system.md`, "The slider control"): every one
 * in the viewer is this, and nothing else draws the slider primitive but the playbar's scrubber.
 *
 * In a panel (the default) it is two lines, shadcn's: a 28px row of the label at the left and the
 * value at the right, then the slider (12px) the control's full width, from the label's left edge to
 * the value's right edge, and 8px under it before the next control: 48px a control, on the panel's
 * inset (`--panel-inset`: the body's padding, none of its own). `inline`: a toolbar row's, one line: the label (the tool's own button or name), the slider,
 * the value. The value is Figma's number field (`SliderValueField.jsx`): one size at rest and edited, its unit muted
 * after the number, stepped by Up and Down and followed by the slider while a number is typed. In a panel, dragging
 * the label sideways scrubs the value, a step a pixel (Shift ten), within the range, as the slider does.
 *
 * @param {{
 *   label: import("react").ReactNode, labelTitle?: string, name: string,
 *   value: number, min: number, max: number, step?: number, origin?: number,
 *   onValueChange(value: number): void, onValueCommit?(value: number): void,
 *   text: string, onTextCommit(draft: string): void, textLabel: string, scale?: number,
 *   hint?: import("react").ReactNode, disabled?: boolean, inline?: boolean, compact?: boolean, className?: string,
 *   thumbProps?: object,
 * }} props `compact`: a settings card's (`SettingsCard.jsx`), its label and value on a 24px line and no gap of its own
 *   under the slider (the card's rows keep their own). `name` is the slider's accessible name, `textLabel` the value's; `hint` a tooltip on the
 *   slider (a joint's range); `scale`, how many of the number `text` shows one of `value` is (a percentage shown
 *   for 0–1: 100). Other props (`data-*`) go on the control's root.
 */
export function SliderField({
  label, labelTitle, name, value, min, max, step = 1, origin, onValueChange, onValueCommit,
  text, onTextCommit, textLabel, scale = 1, hint = null, disabled = false, inline = false, compact = false, className, thumbProps, ...props
}) {
  const scrub = useRef(null);
  // Disabled, the slider alone looks it (half strength, the primitive's, and a not-allowed pointer); its label and its
  // value keep their colours, as Figma's do.
  const slider = <Slider data-slider-field-track="" className={cn(inline ? "h-icon-button min-w-0 flex-1 px-2" : "h-3 min-w-0", "data-[disabled]:cursor-not-allowed")}
    value={[Number(value) || 0]} min={min} max={max} step={step} origin={origin} disabled={disabled}
    thumbProps={{ "aria-label": name, ...thumbProps }}
    onValueChange={next => onValueChange?.(next?.[0] ?? value)}
    onValueCommit={onValueCommit ? next => onValueCommit(next?.[0] ?? value) : undefined} />;
  const field = <SliderValueField text={text} onTextCommit={onTextCommit} value={Number(value) || 0} onValueChange={onValueChange}
    min={min} max={max} step={step} scale={scale} disabled={disabled} ariaLabel={textLabel}
    // In a panel its outline hangs out past the inset by its own 7px (its 6px and its 1px edge), so its value ends on it.
    className={inline ? undefined : "-mr-[7px]"} />;
  // The label scrubs: a step a pixel sideways (Shift ten), on the slider's steps and within its range, written as a
  // slider drag is (`onValueChange` while it moves, `onValueCommit` as it ends). A finger's press scrolls the panel.
  const stepped = next => {
    const size = Number(step) || 1, base = Number.isFinite(min) ? min : 0;
    const snapped = base + Math.round((next - base) / size) * size;
    return Number(clampNumber(snapped, min, max).toFixed(Math.min(10, decimalsOf(size) + 1)));
  };
  const scrubProps = disabled || inline ? {} : {
    onPointerDown: event => {
      if (event.button !== 0 || event.pointerType === "touch") return;
      scrub.current = { x: event.clientX, from: Number(value) || 0, last: Number(value) || 0, moved: false };
      capturePointer(event.currentTarget, event.pointerId);
    },
    onPointerMove: event => {
      const drag = scrub.current;
      if (!drag) return;
      const dx = event.clientX - drag.x;
      if (!drag.moved && Math.abs(dx) < SCRUB_SLOP_PX) return;
      drag.moved = true;
      const next = stepped(drag.from + dx * (Number(step) || 1) * (event.shiftKey ? 10 : 1));
      if (next === drag.last) return;
      drag.last = next;
      onValueChange?.(next);
    },
    onPointerUp: event => {
      const drag = scrub.current;
      scrub.current = null;
      releasePointer(event.currentTarget, event.pointerId);
      if (drag?.moved) onValueCommit?.(drag.last);
    },
    onPointerCancel: () => { scrub.current = null; },
  };
  if (inline) {
    return <div data-slider-field="" data-inline="" className={cn("flex min-w-0 flex-1 items-center gap-1", className)} {...props}>
      {label}
      {hint ? <TooltipHint content={hint}>{slider}</TooltipHint> : slider}
      {field}
    </div>;
  }
  return <div data-slider-field="" className={cn("min-w-0", !compact && "pb-2", className)} {...props}>
    <div className={cn("flex min-w-0 items-center justify-between gap-2", compact ? "h-icon-button" : "h-control")}>
      <TooltipHint content={labelTitle || label} overflowOnly><FieldLabel data-slider-field-label="" {...scrubProps}
        className={cn("select-none", disabled ? "cursor-default" : "cursor-ew-resize touch-pan-y")}>{label}</FieldLabel></TooltipHint>
      {field}
    </div>
    {hint ? <TooltipHint content={hint}>{slider}</TooltipHint> : slider}
  </div>;
}
