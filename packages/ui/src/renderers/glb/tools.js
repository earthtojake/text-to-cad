// A GLB picks nothing: a native glTF scene has no references, so its strip is Display,
// and Animate when the file has clips — orbit, pan and zoom are the viewport's own.

/** What a host command that needs picking is told. A GLB shows the scene as authored; it has no references. */
export const GLB_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A GLB has nothing to select: it is shown as its authored glTF scene, without CAD references. Select on the STEP this GLB was exported from, or control the camera and display settings instead.",
  clearSelection: "A GLB has no selection to clear: it is shown as its authored glTF scene, without CAD references."
});
