import { createToolModes } from "../kit/tools/toolModes.js";

export const ROBOT_TOOL = Object.freeze({ POSE: "pose", SELECT: "select" });

// Select matches the initial Links tab, including files saved under Position.
// Joint values restore independently; only the pointer tool returns to Select.
export const ROBOT_TOOL_MODES = createToolModes({
  defaultMode: ROBOT_TOOL.SELECT,
  modes: { [ROBOT_TOOL.POSE]: { persists: true }, [ROBOT_TOOL.SELECT]: { persists: true } }
});
export const ROBOT_TOOL_RESTORE = Object.freeze({ opensIn: ROBOT_TOOL.SELECT, never: [ROBOT_TOOL.POSE] });

/** What a host command that needs a reference grammar is told. A robot description has none. */
export const ROBOT_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A robot description has no CAD references to select: URDF, SRDF and SDF name links and joints, not faces or edges. Pick a link in the viewport or under Links in the Settings panel, or control the camera and display settings instead."
});
