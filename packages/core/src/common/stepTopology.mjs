export const STEP_TOPOLOGY_EXTENSION = "STEP_topology";
export const STEP_TOPOLOGY_SCHEMA_VERSION = 2;
export const STEP_TOPOLOGY_EDGE_CLASSIFICATION_ALGORITHM = "oc-brep-continuity-v1";
export const STEP_TOPOLOGY_SURFACE_EDGE_ALGORITHM = "oc-polygon-on-triangulation-v1";
export const STEP_TOPOLOGY_EDGE_ANGULAR_TOLERANCE_DEG = 2;
export const STEP_TOPOLOGY_EDGE_SAMPLE_COUNT = 3;
export const STEP_EDGE_BARYCENTRIC_ATTRIBUTE = "_CAD_EDGE_BARYCENTRIC";
export const STEP_EDGE_CLASS_ATTRIBUTE = "_CAD_EDGE_CLASS";

export const STEP_EDGE_FLAGS = Object.freeze({
  DEGENERATE: 1 << 1,
  SEAM: 1 << 2,
  NOT_REFERENCEABLE: 1 << 3,
  BOUNDARY: 1 << 4,
  NON_MANIFOLD: 1 << 5,
  HARD: 1 << 6,
  TANGENT: 1 << 7,
  UNKNOWN_CONTINUITY: 1 << 8
});

export const STEP_EDGE_VISIBILITY_CLASSES = Object.freeze({
  FEATURE: "feature",
  TANGENT: "tangent",
  SEAM: "seam",
  DEGENERATE: "degenerate",
  BOUNDARY: "boundary",
  NON_MANIFOLD: "nonManifold",
  UNKNOWN: "unknown"
});

export const STEP_EDGE_SURFACE_CLASS_CODES = Object.freeze({
  none: 0,
  feature: 1,
  tangent: 2,
  seam: 3,
  degenerate: 4,
  boundary: 5,
  nonManifold: 6,
  unknown: 7
});
export const STEP_EDGE_RENDER_VISIBILITY_CLASSES = Object.freeze([
  STEP_EDGE_VISIBILITY_CLASSES.FEATURE,
  STEP_EDGE_VISIBILITY_CLASSES.TANGENT,
  STEP_EDGE_VISIBILITY_CLASSES.SEAM,
  STEP_EDGE_VISIBILITY_CLASSES.DEGENERATE
]);

export function isCurrentStepTopologySchemaVersion(value) {
  return Number(value) === STEP_TOPOLOGY_SCHEMA_VERSION;
}

export function stepEdgeSurfaceClassCode(edge = {}) {
  const flags = Number(edge?.flags || 0);
  const visibilityClass = String(edge?.visibilityClass || "").trim();
  if (flags & STEP_EDGE_FLAGS.DEGENERATE || visibilityClass === STEP_EDGE_VISIBILITY_CLASSES.DEGENERATE) {
    return STEP_EDGE_SURFACE_CLASS_CODES.degenerate;
  }
  if (flags & STEP_EDGE_FLAGS.SEAM || visibilityClass === STEP_EDGE_VISIBILITY_CLASSES.SEAM) {
    return STEP_EDGE_SURFACE_CLASS_CODES.seam;
  }
  if (flags & STEP_EDGE_FLAGS.BOUNDARY || visibilityClass === STEP_EDGE_VISIBILITY_CLASSES.BOUNDARY) {
    return STEP_EDGE_SURFACE_CLASS_CODES.boundary;
  }
  if (flags & STEP_EDGE_FLAGS.NON_MANIFOLD || visibilityClass === STEP_EDGE_VISIBILITY_CLASSES.NON_MANIFOLD) {
    return STEP_EDGE_SURFACE_CLASS_CODES.nonManifold;
  }
  if (flags & STEP_EDGE_FLAGS.UNKNOWN_CONTINUITY || visibilityClass === STEP_EDGE_VISIBILITY_CLASSES.UNKNOWN) {
    return STEP_EDGE_SURFACE_CLASS_CODES.unknown;
  }
  if (flags & STEP_EDGE_FLAGS.TANGENT || visibilityClass === STEP_EDGE_VISIBILITY_CLASSES.TANGENT) {
    return STEP_EDGE_SURFACE_CLASS_CODES.tangent;
  }
  if (visibilityClass === STEP_EDGE_VISIBILITY_CLASSES.FEATURE || flags & STEP_EDGE_FLAGS.HARD) {
    return STEP_EDGE_SURFACE_CLASS_CODES.feature;
  }
  return STEP_EDGE_SURFACE_CLASS_CODES.feature;
}

export function isDisplayableStepEdgeSurfaceClassCode(value) {
  const code = Number(value);
  return Number.isFinite(code) &&
    code !== STEP_EDGE_SURFACE_CLASS_CODES.none &&
    code !== STEP_EDGE_SURFACE_CLASS_CODES.degenerate;
}

export function stepTopologyCapabilities() {
  return {
    edgeClassification: {
      algorithm: STEP_TOPOLOGY_EDGE_CLASSIFICATION_ALGORITHM,
      angularToleranceDeg: STEP_TOPOLOGY_EDGE_ANGULAR_TOLERANCE_DEG,
      samples: STEP_TOPOLOGY_EDGE_SAMPLE_COUNT
    },
    surfaceEdgeRendering: {
      algorithm: STEP_TOPOLOGY_SURFACE_EDGE_ALGORITHM,
      primitiveAttributes: {
        barycentric: STEP_EDGE_BARYCENTRIC_ATTRIBUTE,
        class: STEP_EDGE_CLASS_ATTRIBUTE
      },
      classCodes: STEP_EDGE_SURFACE_CLASS_CODES,
      visibilityClasses: STEP_EDGE_RENDER_VISIBILITY_CLASSES
    }
  };
}
