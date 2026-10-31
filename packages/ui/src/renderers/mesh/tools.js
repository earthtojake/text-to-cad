import { createToolModes } from "../kit/tools/toolModes.js";

// A 3MF's tools: Select picks its objects — what Quick Edit names (`model.3mf#o2.1`, its build's
// second item, that item's first component) — Pencil, Shapes, Measure (approximate, in the unit the file
// declares) and Clip (a popover from its tile, never a tool in hand). An STL is one mesh in no unit: it has
// Select, Pencil, Shapes and Clip, its Select
// the view's plain navigation (it picks nothing: a Quick Edit names the whole file). Neither has
// parts to move apart.
export const MESH_TOOL = Object.freeze({ SELECT: "select", PENCIL: "pencil", SHAPES: "shapes", MEASURE: "measure" });

export const THREE_MF_TOOL_MODES = createToolModes({
  defaultMode: MESH_TOOL.SELECT,
  modes: { [MESH_TOOL.SELECT]: {}, [MESH_TOOL.PENCIL]: {}, [MESH_TOOL.SHAPES]: {}, [MESH_TOOL.MEASURE]: {} }
});
// An STL opens in Select, as every 3D file does: the view orbits, pans and zooms, and nothing is picked.
export const STL_TOOL_MODES = createToolModes({
  defaultMode: MESH_TOOL.SELECT,
  modes: { [MESH_TOOL.SELECT]: {}, [MESH_TOOL.PENCIL]: {}, [MESH_TOOL.SHAPES]: {} }
});

/** What a host command a mesh file cannot carry out is told. */
export const MESH_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A mesh file has no references a command can select: a 3MF's objects are picked by a person in the viewport under Select (Quick Edit names them, model.3mf#o2.1), and an STL is one mesh, named as the whole file. Control the camera and display settings instead."
});
