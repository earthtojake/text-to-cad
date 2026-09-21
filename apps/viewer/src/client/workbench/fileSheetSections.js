export const FILE_SHEET_SECTION_IDS = Object.freeze({
  STEP_TREE: "tree",
  STEP_MEASUREMENTS: "measurements",
  STEP_REFERENCE: "reference",
  // Two tabs, two independent systems: Pose drives the sidecar's mate graph
  // (sliders per DOF + named presets), Animation plays the sidecar's clips.
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
  DISPLAY: "display",
  RENDER: "render",
  MATERIALS: "materials",
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
  if (options.renderMode === true) {
    return [
      FILE_SHEET_SECTION_IDS.RENDER,
      ...(options.hasMaterialsPanel ? [FILE_SHEET_SECTION_IDS.MATERIALS] : []),
      ...(normalizedKind === "step" && options.hasStepPosePanel
        ? [FILE_SHEET_SECTION_IDS.STEP_POSE]
        : []),
      ...(normalizedKind === "step" && options.hasStepAnimationPanel
        ? [FILE_SHEET_SECTION_IDS.STEP_ANIMATION]
        : []),
      ...(normalizedKind === "mesh" && options.hasEmbeddedGlbAnimationPanel
        ? [FILE_SHEET_SECTION_IDS.STEP_ANIMATION]
        : [])
    ];
  }
  const isSdf = options.isSdf === true || normalizedKind === "sdf";
  const showJoints = options.showJoints !== false;
  const showRobotComponents = options.hasRobotComponents === true;
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
        ...(options.hasDxfLayersPanel ? [FILE_SHEET_SECTION_IDS.DXF_LAYERS] : [])
      ];
    case "step":
      // Display is per-file CAD inspection state. The separate navbar Render
      // mode owns its Studio tab, so it does not appear in this strip.
      return [
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
        FILE_SHEET_SECTION_IDS.DISPLAY
      ];
    case "urdf":
    case "srdf":
    case "sdf":
      // NOTE: no Tree tab yet, though a robot now HAS a link tree and its links are
      // selectable in the viewport. The Tree panel is 556 lines inside StepFileSheet
      // reading 20 props and 33 derived locals; sharing it means extracting it, and a
      // second tree implementation for robots is exactly the parallel stack this effort
      // exists to remove. Components is NOT that tree: it is the flat inventory of
      // named objects inside the linked meshes, and it shares the viewport picker and
      // the Reference inspector rather than the link hierarchy.
      return [
        ...(isSdf ? [FILE_SHEET_SECTION_IDS.ROBOT_SDF] : []),
        ...(options.motionEnabled ? [FILE_SHEET_SECTION_IDS.ROBOT_MOTION] : []),
        // Joints first: posing the robot is what a URDF is opened for, and it is the
        // tab the sheet lands on. Components is the inspection affordance next to it,
        // and it carries its own Reference at its foot rather than owning a tab that
        // stands empty until something is selected.
        ...(showJoints ? [FILE_SHEET_SECTION_IDS.ROBOT_JOINTS] : []),
        ...(showRobotComponents ? [FILE_SHEET_SECTION_IDS.ROBOT_COMPONENTS] : []),
        FILE_SHEET_SECTION_IDS.DISPLAY
      ];
    case "mesh":
      // Direct GLB may add embedded animation. Measurement stays the static
      // triangle tool and is omitted while a native animated hierarchy is live.
      return [
        ...(options.hasEmbeddedGlbAnimationPanel ? [FILE_SHEET_SECTION_IDS.STEP_ANIMATION] : []),
        ...(options.measurementAvailable === false ? [] : [FILE_SHEET_SECTION_IDS.STEP_MEASUREMENTS]),
        FILE_SHEET_SECTION_IDS.DISPLAY
      ];
    default:
      return [];
  }
}

export function defaultOpenFileSheetSectionIds(kind, options = {}) {
  const normalizedKind = normalizeString(kind);
  if (options.renderMode === true) {
    return [FILE_SHEET_SECTION_IDS.RENDER];
  }
  const isSdf = options.isSdf === true || normalizedKind === "sdf";
  const showJoints = options.showJoints !== false;
  switch (normalizedKind) {
    case "dxf":
      return [];
    case "step":
      return [FILE_SHEET_SECTION_IDS.STEP_TREE];
    case "urdf":
    case "srdf":
    case "sdf":
      return [
        ...(isSdf ? [FILE_SHEET_SECTION_IDS.ROBOT_SDF] : []),
        ...(options.motionEnabled ? [FILE_SHEET_SECTION_IDS.ROBOT_MOTION] : []),
        ...(showJoints ? [FILE_SHEET_SECTION_IDS.ROBOT_JOINTS] : [])
      ];
    case "mesh":
      return options.hasEmbeddedGlbAnimationPanel
        ? [FILE_SHEET_SECTION_IDS.STEP_ANIMATION]
        : options.measurementAvailable === false ? [] : [FILE_SHEET_SECTION_IDS.STEP_MEASUREMENTS];
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

export function shouldOpenFileSheetForSelectionReveal({ isDesktop = true, source = "viewer" } = {}) {
  return isDesktop || normalizeString(source) !== "viewer";
}
