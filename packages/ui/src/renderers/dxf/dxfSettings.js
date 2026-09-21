/**
 * What a DXF is shown AS: sheet thickness, stock material, the fold, layer visibility, the
 * display unit and 2D/3D. Everything here is a render-time parameter over the parsed file —
 * nothing reaches back into the `.dxf`, and nothing invalidates anything.
 *
 * All dimensional state is kept in MILLIMETRES (the scene's unit; `parseDxf` has already
 * scaled the file's own `$INSUNITS` into mm). The Units setting converts what the inputs
 * display and accept, at the input boundary only, so switching units never changes the part.
 *
 * Pure data and normalizers: the tabs draw from this, the scene reads it, and the per-file
 * record is written and read through it.
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
 * name, grouped the way their catalog groups them. Each carries a tint for the preview;
 * None (the default) keeps the theme's own surface color.
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

/** Model orientation as quarter-turns about each world axis, applied after the fold. A
 *  folded part often lands facing the wrong way (a U opening down, a flange toward the
 *  camera); quarter-turns re-seat it without free-rotation fiddliness. */
export const DXF_DEFAULT_ORIENTATION = Object.freeze({ x: 0, y: 0, z: 0 });

/** Which way the drawing is being looked at: the 3D fold, or the locked plan view. */
export const DXF_VIEWS = Object.freeze(["3d", "2d"]);
export const DXF_DEFAULT_VIEW = "3d";

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

export function dxfUnitOption(units) {
  return DXF_UNIT_OPTIONS.find((option) => option.value === normalizeDxfUnits(units)) || DXF_UNIT_OPTIONS[0];
}

export function dxfDisplayLength(mm, option) {
  return (Number(mm) || 0) / option.mmPerUnit;
}

export function dxfFormatLength(mm, option) {
  return `${dxfDisplayLength(mm, option).toFixed(option.decimals)} ${option.value}`;
}

/** Parse a typed length in the active unit back to millimetres. */
export function dxfParseLengthToMm(value, option, fallbackMm) {
  const numeric = Number(String(value ?? "").replace(new RegExp(`\\s*${option.value}\\s*$`), ""));
  return Number.isFinite(numeric) ? numeric * option.mmPerUnit : fallbackMm;
}

export function normalizeDxfThicknessMm(value, fallback = DXF_DEFAULT_THICKNESS_MM) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric) || numeric < 0) return fallback;
  return Math.min(DXF_THICKNESS_MAX_MM, Math.max(DXF_THICKNESS_MIN_MM, numeric));
}

export function normalizeDxfBendAngleDeg(value, fallback = DXF_DEFAULT_BEND_ANGLE_DEG) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
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
  if (!Number.isFinite(numeric) || numeric < 0) return fallback;
  return Math.min(DXF_BEND_RADIUS_MAX_MM, numeric);
}

export function normalizeDxfKFactor(value, fallback = DXF_DEFAULT_KFACTOR) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) return fallback;
  return Math.min(DXF_KFACTOR_MAX, Math.max(DXF_KFACTOR_MIN, numeric));
}

export function normalizeDxfOrientation(value) {
  const quarter = (component) => {
    const numeric = Math.trunc(Number(component));
    return Number.isFinite(numeric) ? ((numeric % 4) + 4) % 4 : 0;
  };
  return { x: quarter(value?.x), y: quarter(value?.y), z: quarter(value?.z) };
}

export function normalizeDxfView(value, fallback = DXF_DEFAULT_VIEW) {
  const text = String(value || "").trim().toLowerCase();
  return DXF_VIEWS.includes(text) ? text : fallback;
}

function normalizeHiddenLayers(value) {
  return Array.isArray(value) ? value.map(name => String(name)).filter(Boolean) : [];
}

/** One bend row per bend line the file has, however many the record remembers. */
export function normalizeDxfBends(value, bendCount) {
  return Array.from({ length: Math.max(0, Math.trunc(bendCount) || 0) }, (_, index) => ({
    angleDeg: normalizeDxfBendAngleDeg(value?.[index]?.angleDeg, DXF_DEFAULT_BEND_ANGLE_DEG),
    direction: normalizeDxfBendDirection(value?.[index]?.direction)
  }));
}

/**
 * The renderer's slice of the per-file record, read back. Forgiving: anything missing or
 * unreadable is the default.
 *
 * @param {unknown} raw  `readShellState(view.state).renderer`.
 * @param {number} [bendCount]  How many bend lines the parsed file has. A record is restored
 *   BEFORE the file is parsed, so the default keeps every bend the record remembers; the
 *   rows are sized to the file when the parse lands (`useDxfSettings`). Passing 0 here
 *   instead would quietly throw the remembered angles away.
 */
export function readDxfSettings(raw, bendCount = null) {
  const record = raw && typeof raw === "object" ? raw : {};
  return {
    thicknessMm: normalizeDxfThicknessMm(record.thicknessMm),
    bends: normalizeDxfBends(record.bends, bendCount ?? (Array.isArray(record.bends) ? record.bends.length : 0)),
    bendStyle: normalizeDxfBendStyle(record.bendStyle),
    bendRadiusMm: normalizeDxfBendRadiusMm(record.bendRadiusMm),
    kFactor: normalizeDxfKFactor(record.kFactor),
    hiddenLayers: normalizeHiddenLayers(record.hiddenLayers),
    units: normalizeDxfUnits(record.units),
    orientation: normalizeDxfOrientation(record.orientation),
    material: normalizeDxfMaterial(record.material),
    view: normalizeDxfView(record.view)
  };
}

/** What is written back. Same shape, so a reload of the same build restores exactly. */
export function dxfSettingsRecord(state) {
  return {
    thicknessMm: state.thicknessMm,
    bends: state.bends.map(({ angleDeg, direction }) => ({ angleDeg, direction })),
    bendStyle: state.bendStyle,
    bendRadiusMm: state.bendRadiusMm,
    kFactor: state.kFactor,
    hiddenLayers: [...state.hiddenLayers],
    units: state.units,
    orientation: { ...state.orientation },
    material: state.material,
    view: state.view
  };
}

/**
 * "Reset model": back to the geometry as authored. The display unit and the stock material
 * are how the part is being LOOKED at, not what it is, so they stay — as does the 2D/3D view.
 */
export function resetDxfModel(state) {
  return {
    ...state,
    thicknessMm: DXF_DEFAULT_THICKNESS_MM,
    bends: state.bends.map(() => ({ angleDeg: DXF_DEFAULT_BEND_ANGLE_DEG, direction: "up" })),
    orientation: { ...DXF_DEFAULT_ORIENTATION },
    hiddenLayers: []
  };
}
