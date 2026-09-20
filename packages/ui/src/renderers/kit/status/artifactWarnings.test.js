import assert from "node:assert/strict";
import test from "node:test";

import { artifactWarningItems, buildArtifactWarningAlert } from "./artifactWarnings.js";

const retired = {
  heading: "part.step.js is a retired render module",
  message: "It is read by nothing. Animation is declared with @step(animation=...).",
  recovery: "Move its clips into the decorator and delete part.step.js."
};

test("warnings are read from a payload, an alert, or a bare list", () => {
  assert.deepEqual(artifactWarningItems({ state: "compiled", warnings: [retired] }), [retired]);
  assert.deepEqual(artifactWarningItems({ warnings: [retired] }), [retired]);
  assert.deepEqual(artifactWarningItems([retired]), [retired]);
  assert.deepEqual(artifactWarningItems({ state: "compiled" }), []);
  assert.deepEqual(artifactWarningItems(undefined), []);
  assert.deepEqual(artifactWarningItems({ warnings: "not a list" }), []);
});

test("every field is the server's own wording, trimmed and never invented", () => {
  const [item] = artifactWarningItems({
    warnings: [{ heading: "  Heading  ", message: " Body ", recovery: " Fix it ", extra: "ignored" }]
  });
  assert.deepEqual(item, { heading: "Heading", message: "Body", recovery: "Fix it" });

  // A bare sentence is still an explanation; it has no heading and offers no step.
  assert.deepEqual(artifactWarningItems({ warnings: ["Something is stale."] }), [
    { heading: "", message: "Something is stale.", recovery: "" }
  ]);
});

test("entries with nothing to say are dropped and duplicates collapse", () => {
  assert.deepEqual(
    artifactWarningItems({ warnings: [null, 7, "", { recovery: "orphan step" }, {}] }),
    []
  );
  assert.deepEqual(artifactWarningItems({ warnings: [retired, { ...retired }] }), [retired]);
});

test("the alert is a non-blocking warning that keeps each warning whole", () => {
  const alert = buildArtifactWarningAlert("STEP/part.step", { warnings: [retired] });
  assert.equal(alert.severity, "warning");
  assert.equal(alert.blocking, false);
  assert.equal(alert.compact, true);
  assert.equal(alert.title, "Model warning");
  assert.equal(alert.summary, "Model warning");
  // Flattening into message/recovery would lose the second warning's next step.
  assert.equal(alert.message, undefined);
  assert.equal(alert.recovery, undefined);
  assert.deepEqual(alert.warnings, [retired]);
  assert.equal(
    alert.details,
    `File: STEP/part.step\n${retired.heading} ${retired.message} ${retired.recovery}`
  );
});

test("several warnings are counted, and none at all is no alert", () => {
  const second = { heading: "Second", message: "Another neighbour", recovery: "Remove it." };
  const alert = buildArtifactWarningAlert("part.step", { warnings: [retired, second] });
  assert.equal(alert.title, "2 model warnings");
  assert.equal(alert.warnings.length, 2);
  // details carries every sentence, which is what makes fileStatusAlertKey
  // notice one warning list being replaced by another.
  assert.match(alert.details, /Another neighbour/u);

  assert.equal(buildArtifactWarningAlert("part.step", { warnings: [] }), null);
  assert.equal(buildArtifactWarningAlert("part.step", { state: "compiled" }), null);
  assert.equal(buildArtifactWarningAlert("", undefined), null);
});
