export const DERIVED_DISPLAY_EDGE_TRIANGLE_LIMIT = 500000;

function isNumericArray(value, stride = 1) {
  return (
    (Array.isArray(value) || ArrayBuffer.isView(value)) &&
    value.length >= stride &&
    value.length % stride === 0
  );
}

export function shouldBuildDerivedDisplayEdges(meshData, {
  triangleLimit = DERIVED_DISPLAY_EDGE_TRIANGLE_LIMIT
} = {}) {
  if (isNumericArray(meshData?.edge_indices, 2)) {
    return true;
  }
  const triangleCount = Math.floor((meshData?.indices?.length || 0) / 3);
  return triangleCount <= triangleLimit;
}

// Record edges are drawn when the topology line pass is not: derived mesh
// edges, the wireframe, or the CAD edge lines a surf component carries.
export function shouldShowRecordDisplayEdges({
  edgesVisible = false,
  topologyDisplayEdgesVisible = false,
  displayEdgesVisible = false,
  cadEdgesVisible = false,
  wireframeMode = false
} = {}) {
  return Boolean(
    edgesVisible &&
    !topologyDisplayEdgesVisible &&
    (displayEdgesVisible || cadEdgesVisible || wireframeMode)
  );
}
