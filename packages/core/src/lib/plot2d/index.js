/**
 * Plots: a KiCad board drawn from its file, shared by the CAD Viewer's board view and the headless
 * snapshot bundle. Payload in (`GET /api/v1/documents/kicad_pcb/<id>/plot`, schema 4: geometry per layer), Canvas 2D out in
 * the viewer's two themes (`theme.js`: KiCad's default colours on the dark canvas, the same hues
 * darkened on the light one), the view maths drawing2d's; and the board's Display contract
 * (`boardDisplay.js`), which both read the same way.
 */
export {
  OPTIONAL_LAYER_KINDS,
  PLOT_HAIRLINE_CSS_PX,
  PLOT_SCHEMA_VERSION,
  drawPlot,
  drawPlotImages,
  BOARD_FIT_MARGIN_SHARE,
  boardFitMargin,
  canvasColor,
  fitBoardBounds,
  fitPlotTransform,
  layoutPlot,
  mirrorPageX,
  pageToScreen,
  rectsOverlap,
  screenToPage,
  focusedLayers,
  viewedLayers,
  visiblePageRect
} from "./plot.js";
export { BOARD_PALETTES, HOLE_COLORS, NAME_COLORS, DIM_OPACITY, SCHEMATIC_COLORS, SCHEMATIC_DARK_COLORS, ZONE_OPACITY, boardPalette, itemColor, layerColor,
  netnameColor, schematicColors, schematicItemColor } from "./theme.js";
export { GLYPHS, glyphStrokes, textStrokes } from "./strokeFont.js";
export { boardMirrorX, boardPlanProjection, marksInPlan, planToSheet, sheetToPlan } from "./boardView.js";
export {
  BOARD_DISPLAY_DEFAULTS,
  BOARD_DISPLAY_MODES,
  BOARD_DISPLAY_OTHERS,
  BOARD_DISPLAY_MODE_IDS,
  BOARD_DISPLAY_SIDES,
  BOARD_THROUGH_LAYER_LABELS,
  boardActiveLayer,
  boardDisplayAirwires,
  boardDisplayDrawsCopper,
  boardDisplayIsCustom,
  boardDisplayLayers,
  boardDrawView,
  boardLayerActivatable,
  boardLayerGroups,
  boardModeLayers,
  nextBoardOthers,
  readBoardDisplay,
  selectBoardMode,
  toggleBoardLayer
} from "./boardDisplay.js";
