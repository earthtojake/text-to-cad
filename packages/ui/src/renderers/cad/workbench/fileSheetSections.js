import {
  normalizeFileSheetOpenSectionIds,
  normalizeFileSheetSectionId,
  resolveActiveFileSheetSectionId
} from "../../kit/inspector/activeSection.js";
import { DISPLAY_SECTION_ID } from "../../kit/view-settings/displaySection.js";

export { normalizeFileSheetOpenSectionIds, normalizeFileSheetSectionId, resolveActiveFileSheetSectionId };

export const FILE_SHEET_SECTION_IDS = Object.freeze({
  FILE_STATUS: "status",
  STEP_TREE: "tree",
  STEP_MODELING: "modeling",
  STEP_REFERENCE: "reference",
  KINEMATICS: "kinematics",
  DISPLAY: DISPLAY_SECTION_ID,
  DXF_MATERIAL: "material",
  DXF_BENDS: "bends",
  DXF_LAYERS: "dxfLayers",
  FILE_METADATA: "metadata"
});

function normalizeString(value) {
  return String(value || "").trim();
}

export function renderedFileSheetSectionIds(kind, options = {}) {
  const normalizedKind = normalizeString(kind);
  switch (normalizedKind) {
    // A drawing HAS controls of its own. Thickness (and, where the drawing declares
    // them, bends) are render-time parameters applied to the cached prism rather than bake
    // settings, so they steer the viewport without touching the package.
    case "dxf":
      // One tab per concern: Material (units + stock), Bends (only when the drawing has
      // bend lines), and Layers — the drawing's own STRUCTURE, the DXF analogue of STEP's
      // Tree — whenever the file actually uses layers.
      return [
        FILE_SHEET_SECTION_IDS.DXF_MATERIAL,
        ...(options.hasDxfBendsPanel ? [FILE_SHEET_SECTION_IDS.DXF_BENDS] : []),
        ...(options.hasDxfLayersPanel ? [FILE_SHEET_SECTION_IDS.DXF_LAYERS] : []),
        FILE_SHEET_SECTION_IDS.DISPLAY
      ];
    case "step":
      // Kinematics appears only when the sidecar declares it.
      return [
        FILE_SHEET_SECTION_IDS.STEP_TREE,
        ...(options.hasStepPosePanel || options.hasStepAnimationPanel ? [FILE_SHEET_SECTION_IDS.KINEMATICS] : []),
        FILE_SHEET_SECTION_IDS.DISPLAY
      ];
    default:
      return [];
  }
}

export function defaultOpenFileSheetSectionIds(kind, options = {}) {
  const normalizedKind = normalizeString(kind);
  switch (normalizedKind) {
    case "dxf":
      return [];
    case "step":
      // Open the geometry tree by default.
      return [
        ...(options.hasFileStatus ? [FILE_SHEET_SECTION_IDS.FILE_STATUS] : []),
        FILE_SHEET_SECTION_IDS.STEP_TREE
      ];
    default:
      return [];
  }
}

export function shouldOpenFileSheetForSelectionReveal({ isDesktop = true, source = "viewer" } = {}) {
  return isDesktop || normalizeString(source) !== "viewer";
}
