// A GLB has no tools at all: nothing of a native glTF scene is pickable, so its
// viewport is the camera's alone — orbit, pan and zoom, with no strip over it. A
// file with clips gets the playbar, which is a transport and not a tool.

/** What a host command that needs picking is told. A GLB shows the scene as authored; it has no references. */
export const GLB_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A GLB has nothing to select: it is shown as its authored glTF scene, without CAD references. Select on the STEP this GLB was exported from, or control the camera and display settings instead.",
  clearSelection: "A GLB has no selection to clear: it is shown as its authored glTF scene, without CAD references."
});
