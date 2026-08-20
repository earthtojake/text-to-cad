// Browser tab title. The selected file is appended as "<title> | <filename>";
// index.html carries the same string so the tab reads correctly before hydration.
export const DOCUMENT_TITLE = "text-to-cad";

export const ASSET_STATUS = {
  PENDING: "pending",
  LOADING: "loading",
  READY: "ready",
  ERROR: "error"
};

export const REFERENCE_STATUS = {
  IDLE: "idle",
  DISABLED: "disabled",
  LOADING: "loading",
  READY: "ready",
  ERROR: "error"
};

export { RENDER_FORMAT } from "cadjs/lib/fileFormats.js";

export const TAB_TOOL_MODE = {
  REFERENCES: "references",
  DRAW: "draw",
  MEASURE: "measure",
  PAN: "pan"
};

export const DRAWING_TOOL = {
  FREEHAND: "freehand",
  LINE: "line",
  SURFACE_LINE: "surface-line",
  ARROW: "arrow",
  DOUBLE_ARROW: "double-arrow",
  RECTANGLE: "rectangle",
  CIRCLE: "circle",
  FILL: "fill",
  ERASE: "erase"
};
