import { createToolModes } from "../kit/tools/toolModes.js";

// A plain GLB picks nothing: a native glTF scene has no references, so it has no tool
// strip — orbit, pan and zoom are the viewport's own, and its clips play in preview mode.
// A GLB an implicit part wrote names its LEAVES (one node per primitive in the author's
// code, `cadgen implicit`), and that one selects: Select is its tool, a leaf its reference.

export const GLB_TOOL = Object.freeze({ SELECT: "select" });

/** Select is the one tool, and the one a session restores into. */
export const GLB_TOOL_MODES = createToolModes({
  defaultMode: GLB_TOOL.SELECT,
  modes: { [GLB_TOOL.SELECT]: { persists: true } }
});
export const GLB_TOOL_RESTORE = Object.freeze({ opensIn: GLB_TOOL.SELECT, never: [] });

/** What a host command that needs picking is told for a GLB with no leaves: it has no references. */
export const GLB_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A GLB has nothing to select: it is shown as its authored glTF scene, without CAD references. Select on the STEP this GLB was exported from, or control the camera and display settings instead.",
  clearSelection: "A GLB has no selection to clear: it is shown as its authored glTF scene, without CAD references."
});

/** A GLB with leaves selects leaves by pointer; a host still cannot name one by CAD selector. */
export const GLB_LEAF_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "An implicit part's GLB selects its leaves by pointer, not by CAD selector: there are no faces or occurrences to name. Pick a leaf in the viewport, or open the tape's STEP and select there."
});
