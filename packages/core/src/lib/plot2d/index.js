/**
 * Plots: a document drawn by its own tool (a KiCad board or schematic), shared by the CAD
 * Viewer's plot pane and the headless snapshot bundle. Payload in (`GET /__cad/plot`), Canvas
 * 2D out, the view maths drawing2d's.
 */
export {
  PLOT_SCHEMA_VERSION,
  PLOT_SHEET_GAP,
  drawPlot,
  fitPlotTransform,
  layoutPlot,
  pageToScreen,
  rectsOverlap,
  screenToPage,
  sheetImages,
  visiblePageRect
} from "./plot.js";
export { loadSheetImages } from "./images.js";
