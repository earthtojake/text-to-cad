import { ArrowDown, ArrowUp, RotateCcw, RotateCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Slider } from "@/components/ui/slider";

import {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetButtonRow,
  FileSheetCascadeSelectRow,
  FileSheetControlRow,
  FileSheetSectionBody,
  FileSheetSegmentedControl,
  FileSheetSelectRow,
  FileSheetSliderField,
  FileSheetSubsection,
  FileSheetValueInput
} from "./FileSheet";
import { FILE_SHEET_SECTION_IDS } from "@/workbench/fileSheetSections";

/**
 * The DXF settings tabs, per viewer/docs/settings-ui.md: Material (units + stock) and
 * Bends (fold style + per-bend controls), each a tab of its own with its own Reset.
 *
 * Everything here is a RENDER-TIME parameter. Thickness and boxed bends reshape the cached
 * prism; curved bends re-mesh live from the package's cached contours (geometry.json).
 * Nothing set here can invalidate a package. All dimensional state is kept in MILLIMETRES;
 * the Units setting converts what the inputs display and accept — it sits first because it
 * reframes every dimensional row under it.
 */

export const DXF_THICKNESS_MIN_MM = 0;
export const DXF_THICKNESS_MAX_MM = 25;
export const DXF_THICKNESS_STEP_MM = 0.1;
export const DXF_DEFAULT_THICKNESS_MM = 0;

export const DXF_BEND_ANGLE_MIN_DEG = 0;
export const DXF_BEND_ANGLE_MAX_DEG = 180;
export const DXF_BEND_ANGLE_STEP_DEG = 1;
/** Zero: a flat pattern IS flat, and the dashed bend lines already say where it can fold. */
export const DXF_DEFAULT_BEND_ANGLE_DEG = 0;

export const DXF_BEND_DIRECTIONS = Object.freeze(["up", "down"]);

/** Curved wraps the surface around each bend like real sheet metal — the default, because
 *  the preview should look like the part; Boxed is the mitered fold for a schematic look. */
export const DXF_BEND_STYLES = Object.freeze(["boxed", "curved"]);
export const DXF_DEFAULT_BEND_STYLE = "curved";

/** Inside bend radius in mm; 0 means "auto" (the mesher's visual default, 0.6x thickness). */
export const DXF_BEND_RADIUS_MAX_MM = 20;
export const DXF_DEFAULT_BEND_RADIUS_MM = 0;

/** Where the neutral axis sits within the thickness. 0.44 is the common air-bend value;
 *  0.5 (mid-thickness) is the visual default this preview always used. */
export const DXF_KFACTOR_MIN = 0.1;
export const DXF_KFACTOR_MAX = 0.9;
export const DXF_DEFAULT_KFACTOR = 0.5;

/**
 * The unit the sheet's dimensional inputs display and accept. State stays millimetres —
 * this converts at the input boundary only, so switching units never changes the part.
 */
export const DXF_UNIT_OPTIONS = Object.freeze([
  { value: "mm", label: "Millimetres", mmPerUnit: 1, decimals: 1, sliderStep: 0.1 },
  { value: "cm", label: "Centimetres", mmPerUnit: 10, decimals: 2, sliderStep: 0.01 },
  { value: "in", label: "Inches", mmPerUnit: 25.4, decimals: 2, sliderStep: 0.01 },
  { value: "m", label: "Metres", mmPerUnit: 1000, decimals: 4, sliderStep: 0.0001 }
]);
export const DXF_DEFAULT_UNITS = "mm";

/**
 * Sheet material presets, filled from the SendCutSend catalog
 * (cdn.sendcutsend.com/specs/sendcutsend-catalog-v1.2.json, v1.2): every distinct material
 * name, grouped the way their catalog groups them. Each carries an theme tint for the
 * preview; None (the default) keeps the theme's own surface color.
 */
export const DXF_MATERIAL_PRESETS = Object.freeze([
  { value: "none", label: "None", group: null, colorHex: null },
  { value: "1075-spring-steel", label: "1075 Spring Steel", group: "Metals", colorHex: "#9aa0a8" },
  { value: "2024-t3-aluminum", label: "2024 T3 Aluminum", group: "Metals", colorHex: "#d7dade" },
  { value: "4130-chromoly", label: "4130 Chromoly", group: "Metals", colorHex: "#9aa0a8" },
  { value: "5052-h32-aluminum", label: "5052 H32 Aluminum", group: "Metals", colorHex: "#d7dade" },
  { value: "6061-t6-aluminum", label: "6061 T6 Aluminum", group: "Metals", colorHex: "#d7dade" },
  { value: "7075-t6-aluminum", label: "7075 T6 Aluminum", group: "Metals", colorHex: "#d7dade" },
  { value: "a36-1008-mild-steel", label: "A36/1008 Mild Steel", group: "Metals", colorHex: "#9aa0a8" },
  { value: "ar400-steel", label: "AR400 Steel", group: "Metals", colorHex: "#9aa0a8" },
  { value: "ar500-steel", label: "AR500 Steel", group: "Metals", colorHex: "#9aa0a8" },
  { value: "brass", label: "Brass", group: "Metals", colorHex: "#c9a94f" },
  { value: "copper", label: "Copper", group: "Metals", colorHex: "#c47e5a" },
  { value: "g90-galvanized", label: "G90 Galvanized", group: "Metals", colorHex: "#c4cad1" },
  { value: "grade-2-titanium", label: "Grade 2 Titanium", group: "Metals", colorHex: "#b4b6bd" },
  { value: "grade-5-titanium", label: "Grade 5 Titanium", group: "Metals", colorHex: "#b4b6bd" },
  { value: "high-carbon-1095-steel", label: "High Carbon 1095 Steel", group: "Metals", colorHex: "#9aa0a8" },
  { value: "mic6-cast-aluminum-plate", label: "MIC6 Cast Aluminum Plate", group: "Metals", colorHex: "#d7dade" },
  { value: "stainless-steel-304-series", label: "Stainless Steel (304 Series)", group: "Metals", colorHex: "#c9cdd3" },
  { value: "stainless-steel-316-series", label: "Stainless Steel (316 Series)", group: "Metals", colorHex: "#c9cdd3" },
  { value: "stainless-steel-cpm-magnacut", label: "Stainless Steel Cpm Magnacut", group: "Metals", colorHex: "#c9cdd3" },
  { value: "abs-black", label: "ABS Black", group: "Plastics", colorHex: "#2e3238" },
  { value: "abs-white", label: "ABS White", group: "Plastics", colorHex: "#eceff1" },
  { value: "acrylic-black", label: "Acrylic Black", group: "Plastics", colorHex: "#2e3238" },
  { value: "acrylic-blue", label: "Acrylic Blue", group: "Plastics", colorHex: "#4a7fd4" },
  { value: "acrylic-clear", label: "Acrylic Clear", group: "Plastics", colorHex: "#dfe8ee" },
  { value: "acrylic-dark-grey", label: "Acrylic Dark Grey", group: "Plastics", colorHex: "#5a5f66" },
  { value: "acrylic-green", label: "Acrylic Green", group: "Plastics", colorHex: "#4d9e5f" },
  { value: "acrylic-light-grey", label: "Acrylic Light Grey", group: "Plastics", colorHex: "#b9bec6" },
  { value: "acrylic-mirror", label: "Acrylic Mirror", group: "Plastics", colorHex: "#dfe4ea" },
  { value: "acrylic-red", label: "Acrylic Red", group: "Plastics", colorHex: "#c94a42" },
  { value: "acrylic-white", label: "Acrylic White", group: "Plastics", colorHex: "#eceff1" },
  { value: "acrylic-yellow", label: "Acrylic Yellow", group: "Plastics", colorHex: "#e8c93e" },
  { value: "clear-polypropylene-sheet", label: "Clear Polypropylene Sheet", group: "Plastics", colorHex: "#dfe8ee" },
  { value: "delrin", label: "Delrin", group: "Plastics", colorHex: "#e8e6df" },
  { value: "hdpe-black", label: "HDPE Black", group: "Plastics", colorHex: "#2e3238" },
  { value: "hdpe-white", label: "HDPE White", group: "Plastics", colorHex: "#eceff1" },
  { value: "mylar-clear", label: "Mylar Clear", group: "Plastics", colorHex: "#dfe8ee" },
  { value: "polycarbonate-black", label: "Polycarbonate Black", group: "Plastics", colorHex: "#2e3238" },
  { value: "polycarbonate-clear", label: "Polycarbonate Clear", group: "Plastics", colorHex: "#dfe8ee" },
  { value: "polyethylene-foam", label: "Polyethylene Foam", group: "Plastics", colorHex: "#e5e2da" },
  { value: "uhmw-black", label: "UHMW Black", group: "Plastics", colorHex: "#2e3238" },
  { value: "uhmw-white", label: "UHMW White", group: "Plastics", colorHex: "#eceff1" },
  { value: "chipboard", label: "Chipboard", group: "Wood and MDF", colorHex: "#c9b291" },
  { value: "hardboard", label: "Hardboard", group: "Wood and MDF", colorHex: "#a9835a" },
  { value: "mdf", label: "MDF", group: "Wood and MDF", colorHex: "#c2a075" },
  { value: "plywood-birch", label: "Plywood Birch", group: "Wood and MDF", colorHex: "#d9b98a" },
  { value: "acm-black", label: "ACM Black", group: "Composites", colorHex: "#33363c" },
  { value: "acm-brushed-finish", label: "ACM Brushed Finish", group: "Composites", colorHex: "#c9cdd2" },
  { value: "acm-white", label: "ACM White", group: "Composites", colorHex: "#e9ecef" },
  { value: "carbon-fiber", label: "Carbon Fiber", group: "Composites", colorHex: "#33363c" },
  { value: "g10-black-fiberglass", label: "G10 Black Fiberglass", group: "Composites", colorHex: "#33363c" },
  { value: "phenolic-linen-le", label: "Phenolic Linen Le", group: "Composites", colorHex: "#a98d5f" },
  { value: "garlock-blue-gard-3200", label: "Garlock Blue Gard 3200", group: "Rubber and Gasket", colorHex: "#4a6fa8" },
  { value: "neoprene-rubber-50-60a-duro", label: "Neoprene Rubber (50 60A Duro)", group: "Rubber and Gasket", colorHex: "#33363a" },
  { value: "neoprene-rubber-60a-duro", label: "Neoprene Rubber (60A Duro)", group: "Rubber and Gasket", colorHex: "#33363a" },
  { value: "rubberized-cork", label: "Rubberized Cork", group: "Rubber and Gasket", colorHex: "#b08a5a" },
  { value: "synthetic-nitrile-rubber-nbr-buna-n", label: "Synthetic Nitrile Rubber (nbr, Buna N)", group: "Rubber and Gasket", colorHex: "#33363a" },
  { value: "vhb-double-sided-foam-adhesive-tape", label: "Vhb Double Sided Foam Adhesive Tape", group: "Rubber and Gasket", colorHex: "#33363a" },
  { value: "viton-rubber-fkm", label: "Viton Rubber (fkm)", group: "Rubber and Gasket", colorHex: "#33363a" }
]);
export const DXF_DEFAULT_MATERIAL = "none";

export function normalizeDxfMaterial(value, fallback = DXF_DEFAULT_MATERIAL) {
  const text = String(value || "").trim().toLowerCase();
  return DXF_MATERIAL_PRESETS.some((preset) => preset.value === text) ? text : fallback;
}

export function dxfMaterialPreset(value) {
  return DXF_MATERIAL_PRESETS.find((preset) => preset.value === normalizeDxfMaterial(value))
    || DXF_MATERIAL_PRESETS[0];
}

export function normalizeDxfUnits(value, fallback = DXF_DEFAULT_UNITS) {
  const text = String(value || "").trim().toLowerCase();
  return DXF_UNIT_OPTIONS.some((option) => option.value === text) ? text : fallback;
}

function unitOption(units) {
  return DXF_UNIT_OPTIONS.find((option) => option.value === normalizeDxfUnits(units))
    || DXF_UNIT_OPTIONS[0];
}

function displayLength(mm, option) {
  return (Number(mm) || 0) / option.mmPerUnit;
}

function formatLength(mm, option) {
  return `${displayLength(mm, option).toFixed(option.decimals)} ${option.value}`;
}

/** Parse a typed length in the active unit back to millimetres. */
function parseLengthToMm(value, option, fallbackMm) {
  const numeric = Number(String(value ?? "").replace(new RegExp(`\\s*${option.value}\\s*$`), ""));
  return Number.isFinite(numeric) ? numeric * option.mmPerUnit : fallbackMm;
}

export function normalizeDxfThicknessMm(value, fallback = DXF_DEFAULT_THICKNESS_MM) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) {
    return fallback;
  }
  return Math.min(DXF_THICKNESS_MAX_MM, Math.max(DXF_THICKNESS_MIN_MM, numeric));
}

export function normalizeDxfBendAngleDeg(value, fallback = DXF_DEFAULT_BEND_ANGLE_DEG) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return fallback;
  }
  return Math.min(DXF_BEND_ANGLE_MAX_DEG, Math.max(DXF_BEND_ANGLE_MIN_DEG, numeric));
}

export function normalizeDxfBendDirection(value, fallback = "up") {
  const text = String(value || "").trim().toLowerCase();
  return DXF_BEND_DIRECTIONS.includes(text) ? text : fallback;
}

export function normalizeDxfBendStyle(value, fallback = DXF_DEFAULT_BEND_STYLE) {
  const text = String(value || "").trim().toLowerCase();
  return DXF_BEND_STYLES.includes(text) ? text : fallback;
}

export function normalizeDxfBendRadiusMm(value, fallback = DXF_DEFAULT_BEND_RADIUS_MM) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) {
    return fallback;
  }
  return Math.min(DXF_BEND_RADIUS_MAX_MM, numeric);
}

export function normalizeDxfKFactor(value, fallback = DXF_DEFAULT_KFACTOR) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return fallback;
  }
  return Math.min(DXF_KFACTOR_MAX, Math.max(DXF_KFACTOR_MIN, numeric));
}

/** Model orientation as quarter-turns about each world axis, applied after the fold. A
 *  folded part often lands facing the wrong way (a U opening down, a flange toward the
 *  camera); quarter-turns re-seat it without free-rotation fiddliness. */
export const DXF_DEFAULT_ORIENTATION = Object.freeze({ x: 0, y: 0, z: 0 });

export function normalizeDxfOrientation(value) {
  const quarter = (component) => {
    const numeric = Math.trunc(Number(component));
    return Number.isFinite(numeric) ? ((numeric % 4) + 4) % 4 : 0;
  };
  return {
    x: quarter(value?.x),
    y: quarter(value?.y),
    z: quarter(value?.z)
  };
}

/** The tab-footer Reset (settings-ui.md: outline + RotateCcw, full row, one per tab). */
function DxfResetRow({ label, onReset }) {
  if (!onReset) {
    return null;
  }
  return (
    <FileSheetControlRow label={null}>
      <Button
        type="button"
        variant="outline"
        size="sm"
        className={`${FILE_SHEET_COMPACT_BUTTON_CLASSES} w-full justify-center`}
        onClick={() => onReset()}
        aria-label={label}
        title="Reset"
      >
        <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
        <span>Reset</span>
      </Button>
    </FileSheetControlRow>
  );
}

export function DxfMaterialSettings({
  thicknessMm = DXF_DEFAULT_THICKNESS_MM,
  onThicknessChange,
  units = DXF_DEFAULT_UNITS,
  onUnitsChange,
  material = DXF_DEFAULT_MATERIAL,
  onMaterialChange,
  onReset
}) {
  const activeUnits = normalizeDxfUnits(units);
  const unit = unitOption(activeUnits);
  const thickness = normalizeDxfThicknessMm(thicknessMm);
  const preset = dxfMaterialPreset(material);
  const commitThickness = (next) => onThicknessChange?.(
    normalizeDxfThicknessMm(parseLengthToMm(next, unit, thickness), thickness)
  );

  return (
    <FileSheetSectionBody>
      <FileSheetSubsection>
        {/* Units first: it reframes every dimensional row below it. */}
        <FileSheetSelectRow
          label="Units"
          value={activeUnits}
          onValueChange={(next) => onUnitsChange?.(normalizeDxfUnits(next, activeUnits))}
          options={DXF_UNIT_OPTIONS.map(({ value, label }) => ({ value, label }))}
        />
        <FileSheetCascadeSelectRow
          label="Material"
          value={preset.value}
          onValueChange={(next) => onMaterialChange?.(normalizeDxfMaterial(next, preset.value))}
          options={DXF_MATERIAL_PRESETS.map(({ value, label, group }) => ({ value, label, group }))}
        />
        <FileSheetSliderField
          label="Thickness"
          value={formatLength(thickness, unit)}
          onValueCommit={commitThickness}
          valueInputProps={{
            ariaLabel: "Thickness value",
            min: 0,
            max: displayLength(DXF_THICKNESS_MAX_MM, unit)
          }}
        >
          <Slider
            aria-label="Thickness"
            className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
            value={[displayLength(thickness, unit)]}
            min={0}
            max={displayLength(DXF_THICKNESS_MAX_MM, unit)}
            step={unit.sliderStep}
            onValueChange={([next]) => onThicknessChange?.(
              normalizeDxfThicknessMm(next * unit.mmPerUnit, thickness)
            )}
          />
        </FileSheetSliderField>
      </FileSheetSubsection>

      <DxfResetRow label="Reset material settings" onReset={onReset} />
    </FileSheetSectionBody>
  );
}

export function DxfBendsSettings({
  bends = [],
  onBendChange,
  bendStyle = DXF_DEFAULT_BEND_STYLE,
  onBendStyleChange,
  bendRadiusMm = DXF_DEFAULT_BEND_RADIUS_MM,
  onBendRadiusChange,
  kFactor = DXF_DEFAULT_KFACTOR,
  onKFactorChange,
  units = DXF_DEFAULT_UNITS,
  onRotateOrientation,
  onBendsReset,
  onOrientationReset
}) {
  const style = normalizeDxfBendStyle(bendStyle);
  const radius = normalizeDxfBendRadiusMm(bendRadiusMm);
  const neutralK = normalizeDxfKFactor(kFactor);
  const unit = unitOption(units);

  return (
    <FileSheetSectionBody>
      {/* The per-bend list leads: the angles are what you touch most. One row per bend: the item label IS the slider label, direction rides inline
          beside the value box (settings-ui.md "Repeated item groups", single-row form). */}
      <FileSheetSubsection title="Bends">
        {bends.map((bend, index) => {
          const angle = normalizeDxfBendAngleDeg(bend?.angleDeg);
          const direction = normalizeDxfBendDirection(bend?.direction);
          const commitAngle = (next) => onBendChange?.(index, {
            angleDeg: normalizeDxfBendAngleDeg(next, angle)
          });
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
                    onValueCommit={commitAngle}
                    className="w-12"
                  />
                  <FileSheetSegmentedControl
                    fit
                    ariaLabel={`Bend ${index + 1} direction`}
                    value={direction}
                    onChange={(next) => onBendChange?.(index, {
                      direction: normalizeDxfBendDirection(next, direction)
                    })}
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
                onValueChange={([next]) => commitAngle(next)}
              />
            </FileSheetSliderField>
          );
        })}
        <DxfResetRow label="Reset bend angles" onReset={onBendsReset} />
      </FileSheetSubsection>

      <FileSheetSubsection title="Fold">
        <FileSheetSelectRow
          label="Corners"
          value={style}
          onValueChange={(next) => onBendStyleChange?.(normalizeDxfBendStyle(next, bendStyle))}
          options={[
            { value: "curved", label: "Curved" },
            { value: "boxed", label: "Boxed" }
          ]}
        />
        {/* Sheet-metal bend geometry only means anything when the surface actually
            curves; Boxed is a schematic fold with no radius to size. */}
        {style === "curved" ? (
          <FileSheetSliderField
            label="Radius"
            value={radius > 0 ? formatLength(radius, unit) : "Auto"}
            onValueCommit={(next) => onBendRadiusChange?.(
              normalizeDxfBendRadiusMm(parseLengthToMm(next, unit, radius), radius)
            )}
            valueInputProps={{ ariaLabel: "Bend radius value", className: "w-16" }}
          >
            <Slider
              aria-label="Bend radius"
              className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
              value={[displayLength(radius, unit)]}
              min={0}
              max={displayLength(DXF_BEND_RADIUS_MAX_MM, unit)}
              step={unit.sliderStep}
              onValueChange={([next]) => onBendRadiusChange?.(
                normalizeDxfBendRadiusMm(next * unit.mmPerUnit, radius)
              )}
            />
          </FileSheetSliderField>
        ) : null}
        {style === "curved" ? (
          <FileSheetSliderField
            label="K-factor"
            value={neutralK.toFixed(2)}
            onValueCommit={(next) => onKFactorChange?.(normalizeDxfKFactor(next, neutralK))}
            valueInputProps={{ ariaLabel: "K-factor value", className: "w-16" }}
          >
            <Slider
              aria-label="K-factor"
              className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
              value={[neutralK]}
              min={DXF_KFACTOR_MIN}
              max={DXF_KFACTOR_MAX}
              step={0.01}
              onValueChange={([next]) => onKFactorChange?.(normalizeDxfKFactor(next, neutralK))}
            />
          </FileSheetSliderField>
        ) : null}
      </FileSheetSubsection>

      {/* Model orientation: a folded part often lands facing the wrong way. Sibling
          actions form a button row (equal columns, icon + label, no row label); each click
          turns the model 90 degrees about that world axis. */}
      {onRotateOrientation ? (
        <FileSheetSubsection title="Orientation">
          <FileSheetButtonRow columns={4}>
            {["x", "y", "z"].map((axis) => (
              <Button
                key={axis}
                type="button"
                variant="outline"
                size="sm"
                className={`${FILE_SHEET_COMPACT_BUTTON_CLASSES} justify-center`}
                aria-label={`Rotate model 90 degrees about ${axis.toUpperCase()}`}
                title={`Rotate 90° about ${axis.toUpperCase()}`}
                onClick={() => onRotateOrientation(axis)}
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
              onClick={() => onOrientationReset?.()}
              disabled={!onOrientationReset}
            >
              <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
              <span>Reset</span>
            </Button>
          </FileSheetButtonRow>
        </FileSheetSubsection>
      ) : null}
    </FileSheetSectionBody>
  );
}

export function buildDxfMaterialTab(props) {
  return {
    id: FILE_SHEET_SECTION_IDS.DXF_MATERIAL,
    title: "Material",
    content: <DxfMaterialSettings {...props} />
  };
}

export function buildDxfBendsTab(props) {
  return {
    id: FILE_SHEET_SECTION_IDS.DXF_BENDS,
    title: "Bends",
    content: <DxfBendsSettings {...props} />
  };
}
