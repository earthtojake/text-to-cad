import { createToolModes } from "../kit/tools/toolModes.js";

// A GLB's tools: Select picks its nodes — what Quick Edit names (`model.glb#n12`, the file's
// `nodes[12]`) — Pencil, Shapes, Measure (approximate, in glTF's metres); then Explode where it has several
// rigid nodes that draw, and Clip, popovers from their tiles, never a tool in hand. Its clips play from
// the file sidebar's Animation section.
export const GLB_TOOL = Object.freeze({ SELECT: "select", PENCIL: "pencil", SHAPES: "shapes", MEASURE: "measure" });

export const GLB_TOOL_MODES = createToolModes({
  defaultMode: GLB_TOOL.SELECT,
  modes: Object.fromEntries(Object.values(GLB_TOOL).map(mode => [mode, {}]))
});

/** What a host command a GLB cannot carry out is told. Its nodes are picked by a person. */
export const GLB_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A GLB's nodes are picked by a person in the viewport under Select, and Quick Edit names them (model.glb#n12, the file's nodes[12]); a command cannot select one. Control the camera and display settings instead."
});
