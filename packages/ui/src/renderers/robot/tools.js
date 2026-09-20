import { createToolModes } from "../kit/tools/toolModes.js";
import { SHELL_TOOL } from "../kit/shell/useRendererShell.js";

export const ROBOT_TOOL = Object.freeze({ POSE: "pose", SELECT: "select", DRAW: SHELL_TOOL.DRAW });

// Select is what a session falls back to (ending Draw lands in it, as does a robot with
// nothing to pose); Pose is what a robot OPENS in (`ROBOT_TOOL_RESTORE`). Both are
// recorded by a saved tab; Draw is a session that ends when its tool is asked for again.
export const ROBOT_TOOL_MODES = createToolModes({
  defaultMode: ROBOT_TOOL.SELECT,
  modes: { [ROBOT_TOOL.POSE]: { persists: true }, [ROBOT_TOOL.SELECT]: { persists: true }, [ROBOT_TOOL.DRAW]: { toggles: true } }
});
export const ROBOT_TOOL_RESTORE = Object.freeze({ opensIn: ROBOT_TOOL.POSE });

/** What a host command that needs a reference grammar is told. A robot description has none. */
export const ROBOT_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A robot description has no CAD references to select: URDF, SRDF and SDF name links and joints, not faces or edges. Pick a link in the viewport or the Links tab, or control the camera and display settings instead."
});
