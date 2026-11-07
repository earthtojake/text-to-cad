import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@cad/ui/primitives/select";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { cn } from "@cad/ui/utils";
import { english } from "../../../i18n/core.js";
import {
  FILE_SHEET_SELECT_TRIGGER_CLASSES,
  FileSheetSettingRow,
  parseFileSheetNumberInput
} from "../../kit/inspector/FileSheet.js";
import { SliderField } from "../../kit/inspector/SliderField.jsx";

const TARGET_SLIDER_STEPS = 1000;

/** A slider's step from its range: about a thousand steps across it, a power of ten, never finer than a millionth. */
export function controlStep(control) {
  const range = Math.abs(Number(control.max) - Number(control.min));
  if (!(range > 0)) return 0.01;
  return Number(Math.max(10 ** Math.floor(Math.log10(range / TARGET_SLIDER_STEPS)), 0.000001).toPrecision(12));
}

/**
 * One of Study's What you see controls (`feaControls`: a number or a choice) as its settings-ui.md row: a
 * number is THE slider control (`SliderField`: its label and its committed value over the slider), a choice
 * a select (as Preview's settings draw one), full width with no label where its options say what it is
 * (`hideLabel`). A plain function, not a component: the panel's rows are its own elements, in its own order.
 *
 * @param {{ control: object, value: unknown, onChange(value: unknown): void, valueText(value: number, control: object): string }} props
 *   `control.ariaLabel`: the accessible name, where it differs from its label; `control.step`: a slider's increment,
 *   otherwise about a thousandth of its range.
 */
export function controlRow({ control, value, onChange, valueText, t = english }) {
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
  return (
    <SliderField
      key={control.id}
      data-fea-control={control.id}
      label={label}
      labelTitle={control.labelTitle || label}
      name={name}
      value={Number(value) || 0}
      min={control.min}
      max={control.max}
      step={control.step ?? controlStep(control)}
      onValueChange={(next) => onChange(next)}
      text={valueText(value, control)}
      textLabel={t("fea.controlValue", { name })}
      onTextCommit={(draft) => onChange(parseFileSheetNumberInput(draft, { fallback: value, min: control.min, max: control.max }))}
    />
  );
}
