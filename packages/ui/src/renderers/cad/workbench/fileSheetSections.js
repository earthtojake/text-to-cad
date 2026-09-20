export const FILE_SHEET_SECTION_IDS = Object.freeze({
  FILE_STATUS: "status",
  STEP_TREE: "tree",
  STEP_MODELING: "modeling",
  STEP_REFERENCE: "reference",
  MOTION: "motion",
  VIEW: "view",
  ROBOT_SDF: "sdf",
  ROBOT_COMPONENTS: "components",
  DXF_MATERIAL: "material",
  DXF_BENDS: "bends",
  DXF_LAYERS: "dxfLayers",
  FILE_METADATA: "metadata"
});

function normalizeString(value) {
  return String(value || "").trim();
}

// Per-file active selections keep their meaning across the Motion/View merge.
export function normalizeFileSheetSectionId(value) {
  const id = normalizeString(value);
  if (["pose", "animation", "joints"].includes(id)) return FILE_SHEET_SECTION_IDS.MOTION;
  if (["display", "render"].includes(id)) return FILE_SHEET_SECTION_IDS.VIEW;
  return id;
}

function normalizeSectionIds(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return [...new Set(value.map(normalizeFileSheetSectionId).filter(Boolean))];
}

export function renderedFileSheetSectionIds(kind, options = {}) {
  const normalizedKind = normalizeString(kind);
  const isSdf = options.isSdf === true || normalizedKind === "sdf";
  const showJoints = options.showJoints !== false;
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
        FILE_SHEET_SECTION_IDS.VIEW
      ];
    case "step":
      // Motion combines independently available animation and position controls.
      return [
        FILE_SHEET_SECTION_IDS.STEP_TREE,
        ...(options.hasStepPosePanel || options.hasStepAnimationPanel ? [FILE_SHEET_SECTION_IDS.MOTION] : []),
        FILE_SHEET_SECTION_IDS.VIEW
      ];
    case "urdf":
    case "srdf":
    case "sdf":
      // Robots retain their format-specific document inspector.
      return [
        ...(isSdf ? [FILE_SHEET_SECTION_IDS.ROBOT_SDF] : []),
        // Motion first: posing the robot is what a URDF is opened for, and it is the
        // tab the sheet lands on. Components is the robot's link tree beside it: every
        // description has links, so the tab never depends on what the meshes name, and
        // it carries its own Reference at its foot rather than owning a second tab that
        // stands empty until something is selected.
        ...(showJoints ? [FILE_SHEET_SECTION_IDS.MOTION] : []),
        FILE_SHEET_SECTION_IDS.ROBOT_COMPONENTS,
        FILE_SHEET_SECTION_IDS.VIEW
      ];
    case "mesh":
      // A mesh has nothing to inspect but how it is shown. Measurements belong to the
      // Measure tool's panel under the toolbar, and an embedded GLB clip to the Animate tool.
      return [FILE_SHEET_SECTION_IDS.VIEW];
    default:
      return [];
  }
}

export function defaultOpenFileSheetSectionIds(kind, options = {}) {
  const normalizedKind = normalizeString(kind);
  const isSdf = options.isSdf === true || normalizedKind === "sdf";
  const showJoints = options.showJoints !== false;
  switch (normalizedKind) {
    case "dxf":
      return [];
    case "step":
      // Open the geometry tree by default.
      return [
        ...(options.hasFileStatus ? [FILE_SHEET_SECTION_IDS.FILE_STATUS] : []),
        FILE_SHEET_SECTION_IDS.STEP_TREE
      ];
    case "urdf":
    case "srdf":
    case "sdf":
      return [
        ...(isSdf ? [FILE_SHEET_SECTION_IDS.ROBOT_SDF] : []),
        ...(showJoints ? [FILE_SHEET_SECTION_IDS.MOTION] : [])
      ];
    case "mesh":
      return [];
    default:
      return [];
  }
}

export function normalizeFileSheetOpenSectionIds(sectionIds, renderedSectionIds) {
  const rendered = new Set(normalizeSectionIds(renderedSectionIds));
  if (!rendered.size) {
    return [];
  }
  const open = (Array.isArray(sectionIds) ? sectionIds : []).map(normalizeFileSheetSectionId);
  // Only one section is active. Legacy split lists retain their last available
  // selection, including retired IDs that now point to Motion or View.
  return open.filter(id => rendered.has(id)).slice(-1);
}

// A legacy split can name two active tabs. The last selected available section
// wins, and a missing/unsupported selection falls back to the format's first tab.
export function resolveActiveFileSheetSectionId(openSectionIds, renderedSectionIds) {
  const rendered = normalizeSectionIds(renderedSectionIds);
  return normalizeFileSheetOpenSectionIds(openSectionIds, rendered).at(-1) || rendered[0] || "";
}

export function shouldOpenFileSheetForSelectionReveal({ isDesktop = true, source = "viewer" } = {}) {
  return isDesktop || normalizeString(source) !== "viewer";
}
