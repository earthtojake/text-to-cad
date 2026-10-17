import { createToolModes } from "../kit/tools/toolModes.js";

// A GLB picks nothing: a native glTF scene has no references, so it has no tool strip — orbit,
// pan and zoom are the viewport's own. Its clips play under the Animation tool, its one tool,
// and in preview. One tool needs no strip and is never put down: it is the default mode, up from
// the open (the shell's `SHELL_TOOL.ANIMATE`), so a file with clips has the Animation panel at the
// top-left from the start, with no X, and a static file has nothing there at all.
export const GLB_TOOL_MODES = createToolModes({ defaultMode: "animate", modes: {} });

/** What a host command that needs picking is told. A GLB shows the scene as authored; it has no references. */
export const GLB_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A GLB has nothing to select: it is shown as its authored glTF scene, without CAD references. Select on the STEP this GLB was exported from, or control the camera and display settings instead.",
  clearSelection: "A GLB has no selection to clear: it is shown as its authored glTF scene, without CAD references."
});
