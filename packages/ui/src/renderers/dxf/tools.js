import { createToolModes } from "../kit/tools/toolModes.js";

// A drawing's tools: Select picks its entities — what Quick Edit names (`drawing.dxf#h2F`, the
// entity with handle 2F) — a click the one under it, a plain drag a box (every viewer's) taking the
// entities it touches, Shift at its release adding; a right, middle, Ctrl, Cmd or Shift drag pans, the
// wheel or a pinch zooms, a double-click fits; Draw, the strip's one drawing tool (its `pencil` and `shapes` modes), draws on
// the sheet; Measure takes distances between points snapped to the drawing's ends, centres and lines, in the unit it
// declares. A drawing's Display card holds its Background alone: it has no Projection, Style or Preview.
export const DXF_TOOL = Object.freeze({ SELECT: "select", PENCIL: "pencil", SHAPES: "shapes", MEASURE: "measure" });

export const DXF_TOOL_MODES = createToolModes({
  defaultMode: DXF_TOOL.SELECT,
  modes: Object.fromEntries(Object.values(DXF_TOOL).map(mode => [mode, {}]))
});

/** What a host command a drawing cannot carry out is told. */
export const DXF_DECLINED_LIVE_COMMANDS = Object.freeze({
  select: "A DXF's entities are picked by a person in the viewer under Select, and Quick Edit names them by "
    + "handle (drawing.dxf#h2F, the entity whose handle is 2F); a command cannot select one."
});
export const DXF_NO_CAMERA = "A DXF is a flat drawing shown head on: it has no camera to pose. "
  + "Zoom and pan it in the view, or call resetCamera to fit the whole drawing again.";
export const DXF_NO_DISPLAY = "A DXF's one Display setting is its Background, light or dark, which is the person's, set in the "
  + "view's Display card: the drawing is painted in the pens it declares on that Background, with no surfaces, lighting "
  + "or render mode to configure.";
