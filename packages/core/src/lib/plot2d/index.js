/**
 * Plots: a KiCad board drawn from its file, shared by the CAD Viewer's board view and the headless
 * snapshot bundle. Payload in (`GET /__cad/plot`, schema 3: geometry per layer), Canvas 2D out in
 * KiCad's default colours, the view maths drawing2d's; and the board's Display contract
 * (`boardDisplay.js`), which both read the same way.
 */
export {
  OPTIONAL_LAYER_KINDS,
  PLOT_HAIRLINE_CSS_PX,
  PLOT_SCHEMA_VERSION,
  drawPlot,
  drawPlotImages,
  fitPlotTransform,
  layoutPlot,
  mirrorPageX,
  pageToScreen,
  rectsOverlap,
  screenToPage,
  viewedLayers,
  visiblePageRect
} from "./plot.js";
export { HOLE_COLORS, VIA_COLORS, itemColor, layerColor } from "./theme.js";
export { boardMirrorX, boardPlanProjection, marksInPlan, planToSheet, sheetToPlan } from "./boardView.js";
export {
  BOARD_DISPLAY_DEFAULTS,
  BOARD_DISPLAY_MODES,
  BOARD_DISPLAY_MODE_IDS,
  BOARD_DISPLAY_SIDES,
  BOARD_THROUGH_LAYER_LABELS,
  boardDisplayAirwires,
  boardDisplayDrawsCopper,
  boardDisplayIsCustom,
  boardDisplayLayers,
  boardDrawView,
  boardLayerGroups,
  boardModeLayers,
  readBoardDisplay,
  selectBoardMode,
  toggleBoardLayer
} from "./boardDisplay.js";
