import { useEffect, useRef, useState } from "react";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@cad/ui/primitives/tooltip";
import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import { clampNumber, decimalsOf, formatNumber, readTyped, splitValueText } from "./numberText.js";

// The field, Figma's number field (`docs/design-system.md`, "The slider control"): as wide as what it holds (the number and
// its unit, 22px tall), 32px at least (two or three digits) and 96px at most, its right edge on the slider's, so a longer
// value grows it to the left; no fill at rest, so it sits in the panel as its text does; a 1px outline under the pointer,
// the brand's edge while it is edited and the destructive's while what is typed is no number, 6px in from either so
// neither touches the text. The number is the foreground, its unit after it muted and never edited.
const FIELD_CLASS = [
  "group/value relative box-border inline-flex h-[calc(var(--cad-icon-button)-2px)] w-max min-w-8 max-w-24 shrink-0 cursor-text items-center justify-end gap-[3px] overflow-hidden",
  "rounded-[5px] border border-transparent bg-transparent px-1.5 text-xs leading-(--cad-leading-xs) tabular-nums text-foreground transition-colors",
  "hover:border-foreground/20",
  "data-[editing]:border-brand data-[editing]:bg-background data-[editing]:shadow-[inset_0_0_0_1px_var(--brand)]",
  "data-[invalid]:border-destructive data-[invalid]:shadow-[inset_0_0_0_1px_var(--destructive)]",
  // Disabled, the value keeps its colour (a value is read whether or not it can be set): only the pointer says it is off.
  "data-[disabled]:cursor-not-allowed data-[disabled]:hover:border-transparent",
].join(" ");
const INPUT_CLASS = "m-0 min-w-0 shrink border-0 bg-transparent p-0 text-right text-inherit leading-(--cad-leading-xs) tabular-nums text-foreground shadow-none outline-none ring-0 selection:bg-brand/30 disabled:cursor-not-allowed";

/**
 * The slider control's value (`SliderField.jsx`): the number a slider sets, typed. A click selects the number (its
 * unit is outside the selection); a later click places the caret. Enter or leaving it commits, Escape puts back
 * what it held; Up and Down step it by the control's step, Shift by ten. A length typed in another unit ("5 in" in a
 * millimetre field) is converted, an angle likewise; another unit, or no number, is said under it (the field's edge
 * red), and goes back on Enter. A number past the range says the bound ("Max 9 mm") and is set to it on Enter. While
 * a valid number is typed the slider follows it (`onValueChange`, in the slider's own scale).
 *
 * @param {{ text: string, onTextCommit(text: string): void, value: number, onValueChange?(value: number): void,
 *   min?: number, max?: number, step?: number, scale?: number, disabled?: boolean, ariaLabel: string }} props
 *   `text`: the value as shown, its unit after the number ("7.3 mm", "45°", "60%"); a commit hands back the same
 *   shape. `scale`: how many of the shown number one of the slider's value is (a percentage shown for 0–1: 100);
 *   the bounds and the stride are the slider's. Other props (`data-*`) go on the field.
 */
export function SliderValueField({ text, onTextCommit, value, onValueChange, min, max, step = 1, scale = 1, disabled = false, ariaLabel, className, ...props }) {
  const { t } = useI18n();
  const shown = splitValueText(text);
  const input = useRef(null);
  const [draft, setDraft] = useState(null);
  const editing = draft !== null;
  // What the field held as it was entered (put back by Escape, and what a commit is told apart from), and the
  // slider's value last written while typing (so a value is written once, and put back if it is not kept).
  const start = useRef({ number: shown.number, value });
  const live = useRef(null);
  const pointerFocus = useRef(false);
  const skipBlur = useRef(false);

  const unit = shown.unit, space = shown.space;
  const low = Number.isFinite(min) ? min * scale : -Infinity, high = Number.isFinite(max) ? max * scale : Infinity;
  const shownStep = (Number(step) || 1) * scale;
  const decimals = Math.max(decimalsOf(String(Number(shownStep.toFixed(6)))), decimalsOf(shown.number));
  const withUnit = number => `${number}${unit ? `${space}${unit}` : ""}`;
  // A bound as a hint says it: at the field's precision, with nothing after the point that says nothing ("Max 9 mm").
  const bound = number => String(Number(formatNumber(number, decimals)));

  // What the draft says: its number in the field's unit, and what is wrong with it (said under the field).
  const read = typed => {
    const result = readTyped(typed, unit);
    if (result.kind === "invalid") return { ...result, hint: Number.isFinite(low) && Number.isFinite(high)
      ? t("field.numberBetween", { min: bound(low), max: withUnit(bound(high)) }) : t("field.number") };
    if (result.kind === "unit") return { ...result, hint: t("field.unknownUnit", { unit: result.unit }) };
    if (result.value > high) return { ...result, hint: t("field.max", { value: withUnit(bound(high)) }) };
    if (result.value < low) return { ...result, hint: t("field.min", { value: withUnit(bound(low)) }) };
    return { ...result, hint: "" };
  };
  const state = editing ? read(draft) : null;
  const invalid = Boolean(state && state.kind !== "number");

  // The slider follows a number as it is typed (clamped to its range), never one that is not a number.
  const follow = typed => {
    const result = readTyped(typed, unit);
    if (result.kind !== "number") return;
    // The number the field held typed again is the value it held, not that number rounded (123° for 123.4°).
    const next = result.value === Number(start.current.number) ? start.current.value : clampNumber(result.value, low, high) / scale;
    if (live.current === next || (live.current === null && next === start.current.value)) return;
    live.current = next;
    onValueChange?.(next);
  };
  const putBack = () => {
    if (live.current !== null && live.current !== start.current.value) onValueChange?.(start.current.value);
    live.current = null;
  };

  const begin = () => {
    if (editing) return;
    start.current = { number: shown.number, value };
    live.current = null;
    setDraft(shown.number);
  };
  const finish = commit => {
    if (!editing) return;
    const result = readTyped(draft, unit);
    setDraft(null);
    if (!commit || result.kind !== "number") { putBack(); return; }
    const next = clampNumber(result.value, low, high);
    // A value left as it shows commits nothing: its text may round the value it shows (123.4° as 123).
    if (next === Number(start.current.number)) { putBack(); return; }
    live.current = null;
    // Committed as typed where it is a plain number in range; a bound it was set to at the field's precision; a
    // converted one ("5 in": 127) to four decimals at most, nothing after the point that says nothing.
    const plain = draft.trim();
    const number = next !== result.value ? formatNumber(next, decimals)
      : /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(plain) ? plain
        : String(Number(next.toFixed(Math.max(decimals, 4))));
    onTextCommit?.(withUnit(number));
  };

  // A step from what is typed (or, where that is no number, from what the field held), Shift's ten of them.
  const stepBy = (direction, shift) => {
    const result = readTyped(draft, unit);
    const from = result.kind === "number" ? result.value : Number(start.current.number) || 0;
    const next = clampNumber(from + direction * shownStep * (shift ? 10 : 1), low, high);
    const typed = formatNumber(next, decimals);
    setDraft(typed);
    follow(typed);
    globalThis.requestAnimationFrame?.(() => { if (document.activeElement === input.current) input.current.select(); });
  };

  // A click on the field's padding or its unit is a click on the number.
  const onFieldMouseDown = event => {
    if (disabled || event.target === input.current) return;
    event.preventDefault();
    input.current?.focus();
  };

  useEffect(() => { if (disabled && editing) finish(false); });

  const field = <div {...props} data-slider-field-value-box="" data-editing={editing ? "" : undefined} data-invalid={invalid ? "" : undefined}
    data-disabled={disabled ? "" : undefined} className={cn(FIELD_CLASS, className)} onMouseDown={onFieldMouseDown}>
    <input ref={input} type="text" inputMode="decimal" spellCheck={false} autoComplete="off" aria-label={ariaLabel} aria-invalid={invalid || undefined}
      disabled={disabled} value={editing ? draft : shown.number} data-slider-field-value=""
      className={INPUT_CLASS} style={{ width: `calc(${Math.max(1, String(editing ? draft : shown.number).length)}ch + 1px)` }}
      onPointerDown={event => { if (document.activeElement !== event.currentTarget) pointerFocus.current = true; }}
      onFocus={event => {
        begin();
        // From the keyboard the number is selected at once; from a press, as the press ends (`onMouseUp`).
        if (!pointerFocus.current) {
          // select() focuses the field too: a frame that lands after it was left (Enter at once) must not take it back,
          // nor one after typing began (a key pressed before the frame): it would select what was typed and the next key
          // would replace it.
          const node = event.currentTarget;
          const held = node.value;
          globalThis.requestAnimationFrame?.(() => { if (document.activeElement === node && node.value === held) node.select(); });
        }
      }}
      onMouseUp={event => {
        if (!pointerFocus.current) return;
        pointerFocus.current = false;
        const node = event.currentTarget;
        if (node.selectionStart === node.selectionEnd) { event.preventDefault(); node.select(); }
      }}
      onChange={event => {
        // Typed into with no focus first (a script's change): what it held is what it shows now.
        if (!editing) { start.current = { number: shown.number, value }; live.current = null; }
        setDraft(event.target.value);
        follow(event.target.value);
      }}
      onBlur={() => { pointerFocus.current = false; if (skipBlur.current) { skipBlur.current = false; return; } finish(true); }}
      onKeyDown={event => {
        if (event.key === "Enter") {
          event.preventDefault();
          finish(true);
          skipBlur.current = true;
          event.currentTarget.blur();
          if (document.activeElement === event.currentTarget) skipBlur.current = false;
        } else if (event.key === "Escape") {
          event.preventDefault();
          event.stopPropagation();
          finish(false);
          skipBlur.current = true;
          event.currentTarget.blur();
          if (document.activeElement === event.currentTarget) skipBlur.current = false;
        } else if (event.key === "ArrowUp" || event.key === "ArrowDown") {
          event.preventDefault();
          stepBy(event.key === "ArrowUp" ? 1 : -1, event.shiftKey);
        }
      }} />
    {unit ? <span aria-hidden="true" className="pointer-events-none shrink-0 text-muted-foreground" data-slider-field-unit="">{unit}</span> : null}
  </div>;
  const hint = state?.hint || "";
  return <TooltipProvider delayDuration={0}>
    <Tooltip open={Boolean(hint)}>
      <TooltipTrigger asChild>{field}</TooltipTrigger>
      {hint ? <TooltipContent side="bottom" align="end" sideOffset={4} className="pointer-events-none" data-slider-field-hint=""
        data-hint-kind={state.kind === "number" ? "range" : state.kind}>{hint}</TooltipContent> : null}
    </Tooltip>
  </TooltipProvider>;
}
