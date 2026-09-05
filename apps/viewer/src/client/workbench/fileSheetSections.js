export const FILE_SHEET_SECTION_IDS = Object.freeze({
  FILE_STATUS: "status",
  STEP_TREE: "tree",
  STEP_MEASUREMENTS: "measurements",
  STEP_REFERENCE: "reference",
  // Two tabs, two independent systems: Pose drives the sidecar's mate graph
  // (sliders per DOF + named presets), Animation plays the clips of the render
  // module beside the document (<name>.step.js).
  // A model may ship either, both, or neither, so they are gated separately.
  STEP_POSE: "pose",
  STEP_ANIMATION: "animation",
  ROBOT_SDF: "sdf",
  ROBOT_MOTION: "motion",
  ROBOT_COMPONENTS: "components",
  ROBOT_JOINTS: "joints",
  DXF_MATERIAL: "material",
  DXF_BENDS: "bends",
  DXF_LAYERS: "dxfLayers",
  THEME_DISPLAY: "display",
  FILE_METADATA: "metadata"
});

function normalizeString(value) {
  return String(value || "").trim();
}

function normalizeSectionIds(value) {
  if (!Array.isArray(value)) {
    return [];
  }
  return [...new Set(value.map(normalizeString).filter(Boolean))];
}

export function renderedFileSheetSectionIds(kind, options = {}) {
  const normalizedKind = normalizeString(kind);
  const isSdf = options.isSdf === true || normalizedKind === "sdf";
  const showJoints = options.showJoints !== false;
  const showRobotComponents = options.hasRobotComponents === true;
  const status = options.hasFileStatus ? [FILE_SHEET_SECTION_IDS.FILE_STATUS] : [];
  switch (normalizedKind) {
    // A drawing HAS controls of its own now. Thickness (and, where the drawing declares
    // them, bends) are render-time parameters applied to the cached prism rather than bake
    // settings, so they steer the viewport without touching the package. This used to be
    // status-only on the grounds that the producer owned every setting; it no longer does.
    case "dxf":
      // One tab per concern: Material (units + stock), Bends (only when the drawing has
      // bend lines), and Layers — the drawing's own STRUCTURE, the DXF analogue of STEP's
      // Tree — whenever the file actually uses layers.
      return [
        ...status,
        FILE_SHEET_SECTION_IDS.DXF_MATERIAL,
        ...(options.hasDxfBendsPanel ? [FILE_SHEET_SECTION_IDS.DXF_BENDS] : []),
        ...(options.hasDxfLayersPanel ? [FILE_SHEET_SECTION_IDS.DXF_LAYERS] : [])
      ];
    case "step":
      // Display is the one theme-adjacent tab rendered in the sheet — display
      // mode plus the section-plane and exploded-view transforms, all per-file
      // state. Theme settings are global and live in the navbar theme editor.
      return [
        ...status,
        FILE_SHEET_SECTION_IDS.STEP_TREE,
        FILE_SHEET_SECTION_IDS.STEP_REFERENCE,
        // Pose sits directly after Reference when the model declares mates: it is the
        // one tab here that MOVES the geometry, so it earns the position nearest the
        // default rather than trailing the readouts. Animation follows it — same model,
        // separate system, and present only when the model ships clips.
        ...(options.hasStepPosePanel ? [FILE_SHEET_SECTION_IDS.STEP_POSE] : []),
        ...(options.hasStepAnimationPanel ? [FILE_SHEET_SECTION_IDS.STEP_ANIMATION] : []),
        // Measurements then follows: it and Reference are both readouts about geometry the
        // user has picked, as against the Tree's inventory of what is in the file.
        FILE_SHEET_SECTION_IDS.STEP_MEASUREMENTS,
        FILE_SHEET_SECTION_IDS.THEME_DISPLAY
      ];
    case "urdf":
    case "srdf":
    case "sdf":
      // Named robot objects share the viewport picker and expose a Reference inspector.
      return [
        ...status,
        ...(isSdf ? [FILE_SHEET_SECTION_IDS.ROBOT_SDF] : []),
        ...(options.motionEnabled ? [FILE_SHEET_SECTION_IDS.ROBOT_MOTION] : []),
        ...(showRobotComponents ? [FILE_SHEET_SECTION_IDS.ROBOT_COMPONENTS, FILE_SHEET_SECTION_IDS.STEP_REFERENCE] : []),
        ...(showJoints ? [FILE_SHEET_SECTION_IDS.ROBOT_JOINTS] : [])
      ];
    case "mesh":
      // Measure is the one mesh-specific control: vertex-to-vertex distance on
      // the displayed triangles. Status still only appears when there is an issue.
      return [...status, FILE_SHEET_SECTION_IDS.STEP_MEASUREMENTS];
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
      return [
        ...(options.hasFileStatus ? [FILE_SHEET_SECTION_IDS.FILE_STATUS] : [])
      ];
    case "step":
      // In the tabbed layout the default-active bottom tab is Display, so the
      // STEP default-open list is just the Tree (the default-active top tab).
      return [
        ...(options.hasFileStatus ? [FILE_SHEET_SECTION_IDS.FILE_STATUS] : []),
        FILE_SHEET_SECTION_IDS.STEP_TREE
      ];
    case "urdf":
    case "srdf":
    case "sdf":
      return [
        ...(options.hasFileStatus ? [FILE_SHEET_SECTION_IDS.FILE_STATUS] : []),
        ...(isSdf ? [FILE_SHEET_SECTION_IDS.ROBOT_SDF] : []),
        ...(options.motionEnabled ? [FILE_SHEET_SECTION_IDS.ROBOT_MOTION] : []),
        ...(showJoints ? [FILE_SHEET_SECTION_IDS.ROBOT_JOINTS] : [])
      ];
    case "mesh":
      return [
        ...(options.hasFileStatus ? [FILE_SHEET_SECTION_IDS.FILE_STATUS] : []),
        FILE_SHEET_SECTION_IDS.STEP_MEASUREMENTS
      ];
    default:
      return [];
  }
}

export function normalizeFileSheetOpenSectionIds(sectionIds, renderedSectionIds) {
  const rendered = new Set(normalizeSectionIds(renderedSectionIds));
  if (!rendered.size) {
    return [];
  }
  return [...new Set(normalizeSectionIds(sectionIds)
    .filter((sectionId) => rendered.has(sectionId)))];
}

export function fileSheetSectionIdsWithOpenSection(sectionIds, renderedSectionIds, sectionId) {
  const normalizedSectionId = normalizeString(sectionId);
  const normalizedSectionIds = normalizeFileSheetOpenSectionIds(sectionIds, renderedSectionIds);
  if (!normalizedSectionId || !normalizeSectionIds(renderedSectionIds).includes(normalizedSectionId)) {
    return normalizedSectionIds;
  }
  if (normalizedSectionIds.includes(normalizedSectionId)) {
    return normalizedSectionIds;
  }
  return [...normalizedSectionIds, normalizedSectionId];
}

export function shouldOpenFileSheetForSelectionReveal({ isDesktop = true, source = "viewer" } = {}) {
  return isDesktop || normalizeString(source) !== "viewer";
}
