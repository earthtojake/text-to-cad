import assert from "node:assert/strict";
import test from "node:test";

import { drawingLoadAlert } from "./useDrawingPayload.js";

test("a drawing of another schema says the way out: the page reloaded", () => {
  // It fires when this page's build and the server that drew the payload are of different releases: a
  // page open across a new install, or a card a host keeps.
  const alert = drawingLoadAlert("/models/plate.dxf", { name: "DrawingSchemaError", received: 4, message: "m" });
  assert.equal(alert.recovery, "Reload this page, or restart the app that shows it.");
  assert.equal(alert.reload, true);
});
