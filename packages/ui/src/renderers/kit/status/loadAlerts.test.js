import assert from "node:assert/strict";
import test from "node:test";
import { buildFailedAlert, failureAlert } from "./loadAlerts.js";

test("a failed build is said over the model on screen: what was raised, the traceback in the details", () => {
  const failed = { model: "demo.py::demo", progress: { kind: "build", stage: "body", job: "demo.py::demo", outputs: [], detail: "base", done: 0, total: null, elapsedMs: 9 },
    error: "Traceback (the model's frames):\n  File \"demo.py\", line 17, in block\n    raise ValueError(...)\nValueError: base has no height" };
  const over = buildFailedAlert("XBF/demo.xbf", failed, true);
  assert.equal(over.title, "Couldn’t update the model");
  assert.equal(over.reason, "ValueError: base has no height");
  assert.ok(over.details.includes("Model: demo.py::demo\nStage: Building geometry · base"));
  assert.ok(over.details.endsWith(failed.error));
  // The last version that built stands, so the card is no block (it can be put away); with none, it is the view.
  assert.equal(over.blocking, false);
  const alone = buildFailedAlert("XBF/demo.xbf", { error: "" }, false);
  assert.deepEqual([alone.title, alone.blocking, alone.reason], ["Couldn’t build the model", undefined, "The build returned no diagnostic."]);
});

test("a request that failed says what it was doing in words, and keeps the client's name for it in the details", () => {
  const lost = failureAlert("741015b2", "Failed to fetch", { kind: "network", operation: "engine-document", detail: "Failed to fetch" });
  assert.equal(lost.message, "The browser lost contact with the viewer while loading the model for “741015b2”. Check that the viewer is running and this tab has the correct address, then reload.");
  assert.ok(lost.details.includes("Operation: engine-document"));
  const refused = failureAlert("/m/a.dxf", "", { kind: "http", status: 502, operation: "drawing", detail: "bad gateway" });
  assert.equal(refused.message, "The server returned HTTP 502 while loading the file for “/m/a.dxf”.");
  // An operation already in words is said as it is.
  assert.match(failureAlert("/m/a.step", "", { kind: "network", operation: "preparing display assets", detail: "Failed to fetch" }).message,
    /while preparing display assets for/);
});
