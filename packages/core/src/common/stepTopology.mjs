// The wire names of the STEP_topology GLB extension the render asset clients
// read. cadgen writes the extension (cadgen._internal.glb_topology) and owns
// what its edge flags and class codes mean.
export const STEP_TOPOLOGY_EXTENSION = "STEP_topology";
export const STEP_TOPOLOGY_SCHEMA_VERSION = 2;
export const STEP_EDGE_BARYCENTRIC_ATTRIBUTE = "_CAD_EDGE_BARYCENTRIC";
export const STEP_EDGE_CLASS_ATTRIBUTE = "_CAD_EDGE_CLASS";

export function isCurrentStepTopologySchemaVersion(value) {
  return Number(value) === STEP_TOPOLOGY_SCHEMA_VERSION;
}
