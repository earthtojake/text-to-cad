import assert from "node:assert/strict";
import test from "node:test";

import { drawingLoadAlert } from "./useDrawingPayload.js";

test("a drawing of another schema says the way out: cad-server updated, then the page reloaded", () => {
  // It fires when this page's build and the server that drew the payload are of different releases: a
  // page open across an update, or a card a host keeps.
  const alert = drawingLoadAlert("/models/plate.dxf", { name: "DrawingSchemaError", received: 4, message: "m" });
  assert.equal(alert.recovery, "Update cad-server with the Update button or `cad update`, then reload this page, "
    + "or restart the app that shows it.");
  assert.equal(alert.reload, true);
});
