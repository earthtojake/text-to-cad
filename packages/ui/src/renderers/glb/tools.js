import { createToolModes } from "../kit/tools/toolModes.js";
import { SHELL_TOOL } from "../kit/shell/useRendererShell.js";

/** The plain view tool: nothing of a native glTF scene is pickable, so there is no Select. */
export const GLB_TOOL = Object.freeze({ ORBIT: "orbit", DRAW: SHELL_TOOL.DRAW, ANIMATE: SHELL_TOOL.ANIMATE });

// Orbit is the tool a file opens in and the only one a saved tab records: Draw is
// a session that ends when its tool is asked for again, and Animate's routine is
// released on leaving, so coming back always starts from rest.
export const GLB_TOOL_MODES = createToolModes({
  defaultMode: GLB_TOOL.ORBIT,
  modes: {
    [GLB_TOOL.ORBIT]: { persists: true },
    [GLB_TOOL.DRAW]: { toggles: true },
    [GLB_TOOL.ANIMATE]: {}
  }
});

/** What a host command that needs picking is told. A GLB shows the scene as authored; it has no references. */
export const GLB_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A GLB has nothing to select: it is shown as its authored glTF scene, without CAD references. Select on the STEP this GLB was exported from, or control the camera and display settings instead.",
  clearSelection: "A GLB has no selection to clear: it is shown as its authored glTF scene, without CAD references."
});
