import assert from "node:assert/strict";
import test from "node:test";
import { buildFailedAlert, staleBuildAlert } from "./loadAlerts.js";
import { translator } from "../../../i18n/core.js";

test("a failed build is said over the model on screen: what was raised, the traceback in the details", () => {
  const failed = { model: "demo.py::demo", progress: { phase: "body", label: "Building geometry", detail: "base" },
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

test("a model shown from its last build though its code changed says so, in the page's language, with the command", () => {
  const stale = { text: "cube (id): the code changed since this was built (parts.py changed); run `python /w/parts.py` to build it again",
    changes: ["parts.py changed"], rebuild: "python /w/parts.py" };
  const shown = staleBuildAlert(stale, translator("ja"));
  assert.equal(shown.title, "ビルド後にコードが変更されました");
  assert.equal(shown.recovery, "python /w/parts.py");
  assert.ok(shown.details.startsWith("parts.py changed\n"));
  // A warning beside the model, put away like a failed update; no fault, so no issue is filed.
  assert.deepEqual([shown.severity, shown.blocking, shown.report], ["warning", false, false]);
  assert.equal(staleBuildAlert(stale, translator("en")).title, "The code changed since this was built");
});
