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

export { RENDER_FORMAT } from "@hardcore/core/lib/fileFormats.js";

export const TAB_TOOL_MODE = {
  REFERENCES: "references",
  DRAW: "draw",
  MEASURE: "measure",
  // A session, like Draw: never persisted or restored (`state.js`).
  ANIMATE: "animate",
  // Drag a model's joints by their handles. The tool a robot opens in (`state.js`).
  POSE: "pose"
};

