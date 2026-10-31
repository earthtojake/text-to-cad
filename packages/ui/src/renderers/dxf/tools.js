import { createToolModes } from "../kit/tools/toolModes.js";

// A drawing's tools: Select picks its entities — what Quick Edit names (`drawing.dxf#h2F`, the
// entity with handle 2F) — and is the view's hand: a drag pans, the wheel or a pinch zooms, a
// double-click fits; Pencil and Shapes draw on the sheet; Measure takes distances between points snapped to
// the drawing's ends, centres and lines, in the unit it declares. A drawing has no view controls:
// Display, Projection and Preview are a 3D view's.
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
export const DXF_NO_DISPLAY = "A DXF has no Display settings: a drawing is painted in the pens it declares, on the "
  + "theme's background, with no surfaces, lighting or render mode to configure.";
