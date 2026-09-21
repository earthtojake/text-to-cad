/**
 * 2D drawing rendering, shared by the CAD Viewer's DXF pane and the headless
 * snapshot bundle. Payload in (`GET /__cad/drawing`), Canvas 2D out.
 *
 * Nothing here knows what DXF is: the backend already flattened the file into
 * primitives, and this is the half that turns those primitives into pixels.
 */
export {
  DRAWING_FIT_MARGIN,
  DRAWING_ZOOM_IN_LIMIT,
  DRAWING_ZOOM_OUT_LIMIT,
  clampScale,
  fitTransform,
  modelToScreen,
  panTransform,
  sameTransform,
  screenToModel,
  zoomLimits,
  zoomPercent,
  zoomTransform
} from "./transform.js";
export {
  DRAWING_HAIRLINE_CSS_PX,
  DRAWING_POINT_RADIUS_CSS_PX,
  DRAWING_SCHEMA_VERSION,
  clearSurface,
  drawDrawing,
  prepareDrawing
} from "./drawing.js";
