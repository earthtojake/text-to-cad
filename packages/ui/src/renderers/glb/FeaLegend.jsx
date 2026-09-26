import { clamp } from "@hardcore/core/common/numbers.js";
import { cn } from "@hardcore/ui/utils";
import { Slider } from "@hardcore/ui/primitives/slider";
import { FileSheetSelectRow, FileSheetSliderField, parseFileSheetNumberInput } from "../kit/inspector/FileSheet.js";
import { FLOATING_TOOL_BAR_SURFACE_CLASS } from "../kit/tools/FloatingToolBar.js";
import { deformationRange, feaRampGradient, formatValue } from "./feaResult.js";

/**
 * The legend a GLB with an FEA result gets over its viewport: which field the
 * colours mean and its range, and how much the shown deformation is
 * exaggerated. Both are controls, not just readouts, because the file carries
 * every field and the true displacement (see feaResult.js).
 *
 * Top-left, where nothing else of the shell sits (the view cube is
 * bottom-right, the update status bottom-left, the tool strip top-right).
 * The card itself takes pointer events; the surrounding layer does not, so
 * orbiting past it still works. `field` and `scale` arrive resolved.
 */
export default function FeaLegend({ result, field, scale, onFieldChange, onScaleChange }) {
  const range = deformationRange(result.deformationScale);
  const ticks = [1, 0.75, 0.5, 0.25, 0].map((f) => field.min + (field.max - field.min) * f);
  return (
    <div className="pointer-events-none absolute inset-0 z-20">
      <div
        className={cn("pointer-events-auto absolute left-3 top-3 w-56 rounded-md py-1.5", FLOATING_TOOL_BAR_SURFACE_CLASS)}
        role="group"
        aria-label="FEA result"
      >
        <div className="truncate px-2 pb-1 text-tiny text-muted-foreground" title={result.name}>
          {result.document ? `${result.document} ${result.occurrence}`.trim() : result.name || "FEA result"}
        </div>
        <FileSheetSelectRow
          label="Field"
          ariaLabel="Result field"
          value={field.attribute}
          onValueChange={onFieldChange}
          options={result.fields.map((entry) => ({ value: entry.attribute, label: entry.name }))}
        />
        <div className="flex items-stretch gap-2 px-2 py-1.5">
          <div
            className="w-3 shrink-0 rounded-sm border border-border"
            style={{ background: feaRampGradient(result.ramp), minHeight: "5.5rem" }}
            aria-hidden="true"
          />
          <ol className="flex min-w-0 flex-1 flex-col justify-between font-mono text-micro tabular-nums text-muted-foreground" aria-label={`${field.name} scale`}>
            {ticks.map((value, index) => (
              <li key={index} className="leading-none">
                {formatValue(value)}{index === 0 && field.units ? ` ${field.units}` : ""}
              </li>
            ))}
          </ol>
        </div>
        <FileSheetSliderField
          compact
          label="Deform."
          labelTitle="Deformation scale: how much larger than life the displacement is drawn"
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
      </div>
    </div>
  );
}
