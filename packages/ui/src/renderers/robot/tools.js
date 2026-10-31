import { createToolModes } from "../kit/tools/toolModes.js";

export const ROBOT_TOOL = Object.freeze({ SELECT: "select", PENCIL: "pencil", SHAPES: "shapes", MEASURE: "measure" });

// A robot's tools: Select picks links and drags the joints' knobs, as its filter says
// (`RobotRenderer.jsx`); Pencil and Shapes; Measure (approximate, in the description's metres, each mesh
// as its `scale` draws it); and Clip, a popover from its tile, never a tool in hand. A robot is posed, never exploded. The tool in hand is never
// saved; joint values come back with the file.
export const ROBOT_TOOL_MODES = createToolModes({
  defaultMode: ROBOT_TOOL.SELECT,
  modes: Object.fromEntries(Object.values(ROBOT_TOOL).map(mode => [mode, {}]))
});

/** What a host command a robot cannot carry out is told. Its references are its links, picked by a person. */
export const ROBOT_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A robot description has no faces or edges for a command to select: URDF, SRDF and SDF name links and joints, and a person picks links in the viewport or in the Links panel under Select. Control the camera and display settings instead."
});
