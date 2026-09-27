// A triangle mesh has nothing to pick, measure, pose or play, so an STL or 3MF has
// no tools at all: its viewport is the camera's alone.

/** What a host command that needs picking is told. A mesh is triangles; it carries no references. */
export const MESH_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A mesh file has nothing to select: an STL or 3MF is triangles, without CAD references. Select on the STEP this mesh was exported from, or control the camera and display settings instead.",
  clearSelection: "A mesh file has no selection to clear: an STL or 3MF is triangles, without CAD references."
});
