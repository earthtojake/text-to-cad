// A DXF has nothing to pick, measure, pose or play, so it has no tools at all. Which way the
// drawing is being looked at (2D or 3D) is not a tool either — it is a navbar action, because
// it changes the camera rather than what the pointer does.

/** What a host command that needs picking is told. A DXF is 2D geometry; it carries no CAD references. */
export const DXF_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A DXF has nothing to select: it is a 2D drawing, without CAD references. Select on the STEP this drawing came from, or control the camera, the sheet settings and the display settings instead.",
  clearSelection: "A DXF has no selection to clear: it is a 2D drawing, without CAD references."
});
