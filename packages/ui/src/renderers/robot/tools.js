import { createToolModes } from "../kit/tools/toolModes.js";

export const ROBOT_TOOL = Object.freeze({ POSE: "pose", SELECT: "select" });

// A robot opens in Select, with its Links panel: the tool in hand is never saved. Joint values
// come back with the file (`RobotRenderer.jsx`); only the pointer tool starts over.
export const ROBOT_TOOL_MODES = createToolModes({
  defaultMode: ROBOT_TOOL.SELECT,
  modes: { [ROBOT_TOOL.POSE]: {}, [ROBOT_TOOL.SELECT]: {} }
});

/** What a host command that needs a reference grammar is told. A robot description has none. */
export const ROBOT_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A robot description has no CAD references to select: URDF, SRDF and SDF name links and joints, not faces or edges. Pick a link in the viewport or in the Links panel under Select, or control the camera and display settings instead."
});
