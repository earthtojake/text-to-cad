import { clamp } from "@text-to-cad/core/common/numbers.js";
import { Slider } from "@text-to-cad/ui/primitives/slider";
import { FileSheetFieldGrid, FileSheetSelectRow, FileSheetSliderField, parseFileSheetNumberInput } from "../kit/inspector/FileSheet.js";
import { deformationRange, formatValue } from "./feaResult.js";

/**
 * An FEA result's controls, as the Analysis section of Display: which field the colours show
 * and how much larger than life the displacement is drawn. The file carries every field and
 * the true displacement (feaResult.js), so both are choices, not readouts. `field` and
 * `scale` arrive resolved.
 */
function FeaAnalysisControls({ result, field, scale, onFieldChange, onScaleChange }) {
  const range = deformationRange(result.deformationScale);
  return (
    <>
      <FileSheetFieldGrid columns={1}>
        <FileSheetSelectRow
          hideLabel
          className="px-0"
          label="Field"
          ariaLabel="Result field"
          value={field.attribute}
          onValueChange={onFieldChange}
          options={result.fields.map((entry) => ({ value: entry.attribute, label: entry.name }))}
        />
      </FileSheetFieldGrid>
      <FileSheetSliderField
        label="Deformation"
        labelTitle="How much larger than life the displacement is drawn"
        value={`×${formatValue(scale)}`}
        onValueCommit={(draft) => onScaleChange(parseFileSheetNumberInput(String(draft).replace(/^×/, ""), {
          fallback: scale, min: range.min, max: range.max
        }))}
        valueInputProps={{ ariaLabel: "Deformation scale value" }}
      >
        <Slider
          value={[scale]}
          min={range.min}
          max={range.max}
          step={range.step}
          aria-label="Deformation scale"
          thumbProps={{ "aria-label": "Deformation scale" }}
          onValueChange={(next) => onScaleChange(clamp(next[0], range.min, range.max))}
        />
      </FileSheetSliderField>
    </>
  );
}

/** The section Display adds for a result (`displaySections` of `useRendererShell`). */
export function feaAnalysisSection(props) {
  return { id: "analysis", title: "Analysis", content: <FeaAnalysisControls {...props} /> };
}
