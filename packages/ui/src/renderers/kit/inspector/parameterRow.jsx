import { cn } from "@text-to-cad/ui/utils";
import { Button } from "@text-to-cad/ui/primitives/button";
import { Slider } from "@text-to-cad/ui/primitives/slider";
import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetButtonRow,
  FileSheetCheckboxRow,
  FileSheetColorPicker,
  FileSheetControlRow,
  FileSheetFieldGrid,
  FileSheetSelectRow,
  FileSheetSliderField,
  FileSheetValueInput,
  parseFileSheetNumberInput
} from "./FileSheet.js";
import { formatControlNumber, resolveParameterNumberControlStep, unitSuffix } from "./parameterNumbers.js";

const defaultValueText = (value, parameter) => `${formatControlNumber(value)}${unitSuffix(parameter.unit)}`;

/**
 * One generic parameter (`@text-to-cad/core/common/parameters.js`: number, boolean, enum, color,
 * string, button) as its settings-ui.md row: a slider with its committed value, a select, a
 * checkbox, a colour, a text field or a button. Every panel that shows parameters draws them with
 * this, Position's joints and an FEA result's controls alike, so a type reads the same in both.
 *
 * A plain function, not a component: a panel's rows are its own elements, in its own order.
 *
 * @param {{ parameter: object, value: unknown, onChange(value: unknown): void, labelTitle?: string,
 *   valueText?: (value: number, parameter: object) => string, step?: number }} props
 *   `parameter.ariaLabel`: the control's accessible name, where it differs from its label;
 *   `parameter.hideLabel`: an enum whose options say what it is (a full-width select, no label).
 *   `valueText`: a number's text in its value field (default: its compact figure and unit).
 *   `props.step`: a slider's increment, where the panel sets it; otherwise about a thousandth of its range.
 *   `wideLabel`: a number's label runs over its value field (`FileSheetSliderField`).
 */
export function parameterRow({ parameter, value, onChange, labelTitle, valueText = defaultValueText, step, wideLabel = false }) {
  const label = parameter.label;
  if (parameter.type === "boolean") {
    return <FileSheetCheckboxRow key={parameter.id} label={label} checked={value === true} onCheckedChange={(checked) => onChange(checked)} />;
  }
  if (parameter.type === "enum") {
    const select = <FileSheetSelectRow key={parameter.id} label={label} value={String(value ?? "")} onValueChange={(next) => onChange(next)}
      ariaLabel={parameter.ariaLabel || label} options={parameter.options} {...(parameter.hideLabel ? { hideLabel: true, className: "px-0" } : {})} />;
    return parameter.hideLabel ? <FileSheetFieldGrid key={parameter.id} columns={1}>{select}</FileSheetFieldGrid> : select;
  }
  if (parameter.type === "color") {
    return <FileSheetControlRow key={parameter.id} label={label} trailing={(
      <FileSheetColorPicker value={String(value || "#ffffff")} onChange={(next) => onChange(next)} aria-label={label} />
    )} />;
  }
  if (parameter.type === "button") {
    return <FileSheetButtonRow key={parameter.id}>
      <Button type="button" variant="outline" size="sm" className={cn(FILE_SHEET_COMPACT_BUTTON_CLASSES, "justify-center")}
        onClick={() => onChange(Number(value || 0) + 1)}>{label}</Button>
    </FileSheetButtonRow>;
  }
  if (parameter.type === "string") {
    return <FileSheetControlRow key={parameter.id} label={label} trailing={(
      <FileSheetValueInput value={String(value ?? "")} onValueCommit={(next) => onChange(next)} inputMode="text"
        ariaLabel={`${label} value`} className="w-40 max-w-[min(12rem,55vw)] text-left tabular-nums" />
    )} />;
  }
  const name = parameter.ariaLabel || label;
  return (
    <FileSheetSliderField
      key={parameter.id}
      label={label}
      labelTitle={labelTitle || label}
      wideLabel={wideLabel}
      value={valueText(value, parameter)}
      onValueCommit={(draft) => onChange(parseFileSheetNumberInput(draft, { fallback: value, min: parameter.min, max: parameter.max }))}
      valueInputProps={{ ariaLabel: parameter.ariaLabel ? `${parameter.ariaLabel} value` : `${label} slider value` }}
    >
      <Slider
        className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
        value={[Number(value) || 0]}
        min={parameter.min}
        max={parameter.max}
        step={step ?? resolveParameterNumberControlStep(parameter)}
        onValueChange={(next) => onChange(next?.[0] ?? value)}
        thumbProps={{ "aria-label": name }}
      />
    </FileSheetSliderField>
  );
}
