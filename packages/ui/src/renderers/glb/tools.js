import { createToolModes } from "../kit/tools/toolModes.js";

// A GLB picks nothing: a native glTF scene has no references, so it has no tool strip — orbit,
// pan and zoom are the viewport's own, and its clips play in preview mode. An FEA result is the
// exception: its faces are its source STEP's, so it has Select, whose panel is its Study.
export const GLB_TOOL = Object.freeze({ SELECT: "select" });

// An FEA result opens in Select, with Study up; the tool in hand is never saved.
export const GLB_TOOL_MODES = createToolModes({ defaultMode: GLB_TOOL.SELECT, modes: { [GLB_TOOL.SELECT]: {} } });

/** What a host command that needs picking is told. A GLB shows the scene as authored; it has no references. */
export const GLB_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A GLB has nothing to select: it is shown as its authored glTF scene, without CAD references. Select on the STEP this GLB was exported from, or control the camera and display settings instead.",
  clearSelection: "A GLB has no selection to clear: it is shown as its authored glTF scene, without CAD references."
});
