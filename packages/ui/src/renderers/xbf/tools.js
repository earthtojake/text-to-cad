import { createToolModes } from "../kit/tools/toolModes.js";

// An engine document's tools are a STEP's, in a STEP's order: Select (its filter on the chevron
// after it), Draw (the strip's one drawing tool, over the `pencil` and `shapes` modes), Measure (its own filter after
// it); then the model's effects, Explode (where it places two or more parts) and Clip, each a tool of the strip as Draw
// is: pressed, it is in hand, its row under the strip, standing over Select (`kit/tools/model-effects/ModelTools.jsx`).
export const XBF_TOOL = Object.freeze({ SELECT: "select", PENCIL: "pencil", SHAPES: "shapes", MEASURE: "measure" });

export const XBF_TOOL_MODES = createToolModes({
  defaultMode: XBF_TOOL.SELECT,
  modes: Object.fromEntries(Object.values(XBF_TOOL).map(mode => [mode, {}]))
});

/** What a host command an engine document cannot carry out is told. */
export const XBF_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "An engine document's parts, faces and edges are picked by a person in the viewport or the model tree under Select (each named as the document names it); a command cannot select them. Control the camera and display settings instead."
});
