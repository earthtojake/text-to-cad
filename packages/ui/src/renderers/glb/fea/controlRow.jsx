import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@text-to-cad/ui/primitives/select";
import { Slider } from "@text-to-cad/ui/primitives/slider";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import { english } from "../../../i18n/core.js";
import {
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FILE_SHEET_SELECT_TRIGGER_CLASSES,
  FileSheetSettingRow,
  FileSheetSliderField,
  parseFileSheetNumberInput
} from "../../kit/inspector/FileSheet.js";

const TARGET_SLIDER_STEPS = 1000;

// A value box as wide as the widest value its control shows (its range's ends and the value now), so it never
// changes width as the value moves: with tabular figures a figure and the "×" are each 1ch and a point half
// of one, and half a ch more is spare; then the padding (0.75rem) and the box's 1px borders. "×6000" is
// 6ch, "×12.0" 5ch, "×9500000" 9ch, so a large exaggeration's last figures are never cut off. It overrides
// the sheet's own width, which a joint's figure fits.
const VALUE_WIDTHS = ["w-[calc(3ch+0.75rem+2px)]", "w-[calc(4ch+0.75rem+2px)]", "w-[calc(5ch+0.75rem+2px)]",
  "w-[calc(6ch+0.75rem+2px)]", "w-[calc(7ch+0.75rem+2px)]", "w-[calc(8ch+0.75rem+2px)]", "w-[calc(9ch+0.75rem+2px)]",
  "w-[calc(10ch+0.75rem+2px)]", "w-[calc(11ch+0.75rem+2px)]", "w-[calc(12ch+0.75rem+2px)]", "w-[calc(13ch+0.75rem+2px)]",
  "w-[calc(14ch+0.75rem+2px)]"];
const textCh = (text) => [...String(text ?? "")].reduce((sum, glyph) => sum + (glyph === "." || glyph === "," ? 0.5 : 1), 0) + 0.5;
const valueInputWidth = (texts) => {
  const ch = Math.ceil(Math.max(...texts.map(textCh)));
  return VALUE_WIDTHS[Math.min(Math.max(ch, 3), 14) - 3];
};

/** A slider's step from its range: about a thousand steps across it, a power of ten, never finer than a millionth. */
export function controlStep(control) {
  const range = Math.abs(Number(control.max) - Number(control.min));
  if (!(range > 0)) return 0.01;
  return Number(Math.max(10 ** Math.floor(Math.log10(range / TARGET_SLIDER_STEPS)), 0.000001).toPrecision(12));
}

/**
 * One of Study's What you see controls (`feaControls`: a number or a choice) as its settings-ui.md row: a
 * number is a slider with its committed value (`FileSheetSliderField`), a choice a select (as Preview's
 * settings draw one), full width with no label where its options say what it is (`hideLabel`).
 * A plain function, not a component: the panel's rows are its own elements, in its own order.
 *
 * @param {{ control: object, value: unknown, onChange(value: unknown): void, valueText(value: number, control: object): string,
 *   boxTexts?: string[] | null }} props  `boxTexts`: the values its box is sized to hold, where rows share one width;
 *   else its own range's ends and its value.
 *   `control.ariaLabel`: the accessible name, where it differs from its label; `control.step`: a slider's increment,
 *   otherwise about a thousandth of its range.
 */
export function controlRow({ control, value, onChange, valueText, t = english, boxTexts = null }) {
  const label = control.label;
  const name = control.ariaLabel || label;
  if (control.type === "enum") {
    const select = <Select value={String(value ?? "")} onValueChange={(next) => onChange(next)}>
      <TooltipHint content={control.hideLabel ? name : undefined}>
        <SelectTrigger aria-label={name} size="sm" className={cn(FILE_SHEET_SELECT_TRIGGER_CLASSES, "!h-6 w-full min-w-0")}><SelectValue /></SelectTrigger>
      </TooltipHint>
      <SelectContent>{(control.options || []).map((option) => <SelectItem key={option.value} value={option.value}>{option.label}</SelectItem>)}</SelectContent>
    </Select>;
    return control.hideLabel
      ? <div key={control.id} className="min-w-0 px-2" data-fea-control={control.id}>{select}</div>
      : <FileSheetSettingRow key={control.id} label={label}>{select}</FileSheetSettingRow>;
  }
  const text = valueText(value, control);
  return (
    <FileSheetSliderField
      key={control.id}
      label={label}
      labelTitle={control.labelTitle || label}
      value={text}
      onValueCommit={(draft) => onChange(parseFileSheetNumberInput(draft, { fallback: value, min: control.min, max: control.max }))}
      valueInputProps={{ ariaLabel: t("fea.controlValue", { name }),
        className: valueInputWidth(boxTexts || [text, valueText(control.min, control), valueText(control.max, control)]) }}
    >
      <Slider
        className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
        value={[Number(value) || 0]}
        min={control.min}
        max={control.max}
        step={control.step ?? controlStep(control)}
        onValueChange={(next) => onChange(next?.[0] ?? value)}
        thumbProps={{ "aria-label": name }}
      />
    </FileSheetSliderField>
  );
}
