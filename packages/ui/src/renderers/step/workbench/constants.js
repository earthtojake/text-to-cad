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

export const TAB_TOOL_MODE = {
  REFERENCES: "references",
  DRAW: "draw",
  MEASURE: "measure",
  EXPLODE: "exploded",
  CLIP: "clip",
  // Drag a model's joints by their handles. Offered, never restored into (`state.js`).
  POSE: "pose",
  // Play the model's routines in the tools view: the shell's tool (`SHELL_TOOL.ANIMATE`), as Draw is.
  ANIMATE: "animate"
};


// This renderer's tool modes for the kit's state machine (`kit/tools/toolModes.js`).
// Draw and Animation toggle off on repeated activation. Measure stays armed; its result-aware
// toolbar action clears retained measurements explicitly. The tool in hand is never
// saved: a file opens in Select, with its pose intact, rather than with the handles
// already up over a model the person has not looked at yet.
export const CAD_TOOL_MODES = createToolModes({
  defaultMode: TAB_TOOL_MODE.REFERENCES,
  modes: {
    [TAB_TOOL_MODE.REFERENCES]: {},
    [TAB_TOOL_MODE.MEASURE]: {},
    [TAB_TOOL_MODE.EXPLODE]: {},
    [TAB_TOOL_MODE.CLIP]: {},
    [TAB_TOOL_MODE.DRAW]: { toggles: true },
    [TAB_TOOL_MODE.POSE]: {},
    [TAB_TOOL_MODE.ANIMATE]: { toggles: true }
  }
});
