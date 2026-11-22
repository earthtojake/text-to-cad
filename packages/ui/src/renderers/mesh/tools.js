import { createToolModes } from "../kit/tools/toolModes.js";

// A mesh file's tools. Select picks its parts — what Quick Edit names: a 3MF's objects (`model.3mf#o2.1`, its build's
// second item, that item's first component), an STL's bodies (`model.stl#b2`, `stlBodies.js`) — then Draw (over the
// `pencil` and `shapes` modes) and Clip (a tool of the strip as Draw is, its row under the strip); a 3MF also has
// Measure (approximate, in the unit the file declares), and an STL, in no unit, none. Neither has parts to move apart.
export const MESH_TOOL = Object.freeze({ SELECT: "select", PENCIL: "pencil", SHAPES: "shapes", MEASURE: "measure" });

export const THREE_MF_TOOL_MODES = createToolModes({
  defaultMode: MESH_TOOL.SELECT,
  modes: { [MESH_TOOL.SELECT]: {}, [MESH_TOOL.PENCIL]: {}, [MESH_TOOL.SHAPES]: {}, [MESH_TOOL.MEASURE]: {} }
});
// An STL opens in Select, as every 3D file does.
export const STL_TOOL_MODES = createToolModes({
  defaultMode: MESH_TOOL.SELECT,
  modes: { [MESH_TOOL.SELECT]: {}, [MESH_TOOL.PENCIL]: {}, [MESH_TOOL.SHAPES]: {} }
});

/** What a host command a mesh file cannot carry out is told. Its parts are picked by a person. */
export const MESH_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A mesh file's objects and bodies are picked by a person in the viewport under Select, and Quick Edit names them (model.3mf#o2.1, model.stl#b2); a command cannot select one. Control the camera and display settings instead."
});
