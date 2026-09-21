import { ArrowDown, ArrowUp, RotateCcw, RotateCw } from "lucide-react";
import { Button } from "@hardcore/ui/primitives/button";
import { Slider } from "@hardcore/ui/primitives/slider";
import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES, FILE_SHEET_PRECISION_SLIDER_CLASSES, FileSheetButtonRow,
  FileSheetSectionBody, FileSheetSegmentedControl, FileSheetSelectRow, FileSheetSliderField,
  FileSheetSubsection, FileSheetValueInput
} from "../../kit/inspector/FileSheet.js";
import {
  DXF_BEND_ANGLE_MAX_DEG, DXF_BEND_ANGLE_MIN_DEG, DXF_BEND_ANGLE_STEP_DEG, DXF_BEND_RADIUS_MAX_MM,
  DXF_KFACTOR_MAX, DXF_KFACTOR_MIN, dxfDisplayLength, dxfFormatLength, dxfParseLengthToMm,
  dxfUnitOption, normalizeDxfBendAngleDeg, normalizeDxfBendDirection, normalizeDxfBendRadiusMm,
  normalizeDxfBendStyle, normalizeDxfKFactor
} from "../dxfSettings.js";
import { DxfResetRow } from "./DxfResetRow.jsx";

/** How the flat pattern folds: an angle and a direction per crease, the corner geometry, and
 *  which way the folded part ends up facing. */
export function BendsTab({ settings }) {
  const { state } = settings;
  const style = normalizeDxfBendStyle(state.bendStyle);
  const radius = normalizeDxfBendRadiusMm(state.bendRadiusMm);
  const neutralK = normalizeDxfKFactor(state.kFactor);
  const unit = dxfUnitOption(state.units);

  return (
    <FileSheetSectionBody>
      {/* The per-bend list leads: the angles are what you touch most. One row per bend: the item label IS the
          slider label, direction rides inline beside the value box (settings-ui.md "Repeated item groups"). */}
      <FileSheetSubsection title="Bends">
        {state.bends.map((bend, index) => {
          const angle = normalizeDxfBendAngleDeg(bend?.angleDeg);
          const direction = normalizeDxfBendDirection(bend?.direction);
          return (
            <FileSheetSliderField
              key={index}
              label={`Bend ${index + 1}`}
              value={`${Math.round(angle)}°`}
              trailing={(
                <div className="flex shrink-0 items-center gap-1.5">
                  <FileSheetValueInput
                    ariaLabel={`Bend ${index + 1} angle value`}
                    value={`${Math.round(angle)}°`}
                    onValueCommit={next => settings.changeBend(index, { angleDeg: next })}
                    className="w-12"
                  />
                  <FileSheetSegmentedControl
                    fit
                    ariaLabel={`Bend ${index + 1} direction`}
                    value={direction}
                    onChange={next => settings.changeBend(index, { direction: next })}
                    options={[
                      { value: "up", label: "Up", title: "Bend up", Icon: ArrowUp, iconOnly: true },
                      { value: "down", label: "Down", title: "Bend down", Icon: ArrowDown, iconOnly: true }
                    ]}
                  />
                </div>
              )}
            >
              <Slider
                aria-label={`Bend ${index + 1} angle`}
                className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
                value={[angle]}
                min={DXF_BEND_ANGLE_MIN_DEG}
                max={DXF_BEND_ANGLE_MAX_DEG}
                step={DXF_BEND_ANGLE_STEP_DEG}
                onValueChange={([next]) => settings.changeBend(index, { angleDeg: next })}
              />
            </FileSheetSliderField>
          );
        })}
        <DxfResetRow label="Reset bend angles" onReset={settings.resetBends} />
      </FileSheetSubsection>

      <FileSheetSubsection title="Fold">
        <FileSheetSelectRow
          label="Corners"
          value={style}
          onValueChange={next => settings.setBendStyle(next)}
          options={[{ value: "curved", label: "Curved" }, { value: "boxed", label: "Boxed" }]}
        />
        {/* Sheet-metal bend geometry only means anything when the surface actually curves;
            Boxed is a schematic fold with no radius to size. */}
        {style === "curved" ? (
          <FileSheetSliderField
            label="Radius"
            value={radius > 0 ? dxfFormatLength(radius, unit) : "Auto"}
            onValueCommit={next => settings.setBendRadius(dxfParseLengthToMm(next, unit, radius))}
            valueInputProps={{ ariaLabel: "Bend radius value", className: "w-16" }}
          >
            <Slider
              aria-label="Bend radius"
              className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
              value={[dxfDisplayLength(radius, unit)]}
              min={0}
              max={dxfDisplayLength(DXF_BEND_RADIUS_MAX_MM, unit)}
              step={unit.sliderStep}
              onValueChange={([next]) => settings.setBendRadius(next * unit.mmPerUnit)}
            />
          </FileSheetSliderField>
        ) : null}
        {style === "curved" ? (
          <FileSheetSliderField
            label="K-factor"
            value={neutralK.toFixed(2)}
            onValueCommit={next => settings.setKFactor(next)}
            valueInputProps={{ ariaLabel: "K-factor value", className: "w-16" }}
          >
            <Slider
              aria-label="K-factor"
              className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
              value={[neutralK]}
              min={DXF_KFACTOR_MIN}
              max={DXF_KFACTOR_MAX}
              step={0.01}
              onValueChange={([next]) => settings.setKFactor(next)}
            />
          </FileSheetSliderField>
        ) : null}
      </FileSheetSubsection>

      {/* Model orientation: a folded part often lands facing the wrong way. Sibling actions
          form a button row (equal columns, icon + label, no row label); each click turns the
          model 90 degrees about that world axis. */}
      <FileSheetSubsection title="Orientation">
        <FileSheetButtonRow columns={4}>
          {["x", "y", "z"].map(axis => (
            <Button
              key={axis}
              type="button"
              variant="outline"
              size="sm"
              className={`${FILE_SHEET_COMPACT_BUTTON_CLASSES} justify-center`}
              aria-label={`Rotate model 90 degrees about ${axis.toUpperCase()}`}
              title={`Rotate 90° about ${axis.toUpperCase()}`}
              onClick={() => settings.rotate(axis)}
            >
              <RotateCw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
              <span>{axis.toUpperCase()} 90°</span>
            </Button>
          ))}
          <Button
            type="button"
            variant="outline"
            size="sm"
            className={`${FILE_SHEET_COMPACT_BUTTON_CLASSES} justify-center`}
            aria-label="Reset model orientation"
            title="Reset orientation"
            onClick={() => settings.resetOrientation()}
          >
            <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
            <span>Reset</span>
          </Button>
        </FileSheetButtonRow>
      </FileSheetSubsection>
    </FileSheetSectionBody>
  );
}
