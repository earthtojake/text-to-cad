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

import { createToolModes } from "../../kit/tools/toolModes.js";

export { RENDER_FORMAT } from "@hardcore/core/lib/fileFormats.js";

export const TAB_TOOL_MODE = {
  REFERENCES: "references",
  DRAW: "draw",
  MEASURE: "measure",
  // A session, like Draw: never persisted or restored (`state.js`).
  ANIMATE: "animate",
  // Drag a model's joints by their handles. Offered, never restored into (`state.js`).
  POSE: "pose"
};


// This renderer's tool modes for the kit's state machine (`kit/tools/toolModes.js`).
// Measure and Draw are sessions that end when their tool is asked for again; a saved
// tab records only Select, Measure and Pose.
export const CAD_TOOL_MODES = createToolModes({
  defaultMode: TAB_TOOL_MODE.REFERENCES,
  modes: {
    [TAB_TOOL_MODE.REFERENCES]: { persists: true },
    [TAB_TOOL_MODE.MEASURE]: { toggles: true, persists: true },
    [TAB_TOOL_MODE.DRAW]: { toggles: true },
    [TAB_TOOL_MODE.ANIMATE]: {},
    [TAB_TOOL_MODE.POSE]: { persists: true }
  }
});
