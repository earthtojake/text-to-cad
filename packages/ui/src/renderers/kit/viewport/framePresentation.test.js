import assert from "node:assert/strict";
import test from "node:test";
import { createFramePresentation, viewerTransitionBackdrop } from "./framePresentation.js";

test("Render stays covered until both geometry and the studio can produce a frame", () => {
  const canvas = { style: {} }, events = [];
  const presentation = createFramePresentation({ canvas, renderMode: true, onPresent: (key) => events.push(`present:${key}`) });
  const draw = () => { assert.equal(canvas.style.visibility, "hidden"); events.push("draw"); };
  assert.equal(presentation.draw({ hasVisibleModel: false, environmentReady: true }, draw, { key: "part:complete", ready: true }), false);
  assert.equal(presentation.draw({ hasVisibleModel: true, environmentReady: false }, draw, { key: "part:complete", ready: true }), false);
  assert.deepEqual(events, []);
  presentation.draw({ hasVisibleModel: true, environmentReady: true }, draw, { key: "part:complete", ready: true });
  assert.deepEqual(events, ["draw", "present:part:complete"]);
  assert.equal(canvas.style.visibility, "visible");
  presentation.draw({ hasVisibleModel: true, environmentReady: true }, () => events.push("orbit"), { key: "part:complete", ready: true });
  assert.deepEqual(events, ["draw", "present:part:complete", "orbit"], "orbit does not restart loading");
  presentation.draw({ hasVisibleModel: false }, () => events.push("clear"), { key: "next", ready: false });
  assert.equal(events.at(-1), "clear", "clearing an existing model must not leave its old pixels visible");
});

test("Inspect can present without constructing a photographic environment", () => {
  const canvas = { style: {} };
  const presentation = createFramePresentation({ canvas, renderMode: false });
  assert.equal(presentation.draw({ hasVisibleModel: true }, () => {}, { key: "part:partial", ready: true }), true);
  assert.equal(canvas.style.visibility, "visible");
});

test("a reconciled key is acknowledged once after drawing without hiding the prior view", () => {
  const canvas = { style: {} }, events = [];
  const presentation = createFramePresentation({ canvas, renderMode: false, onPresent: (key) => events.push(key) });
  const runtime = { hasVisibleModel: true };
  presentation.draw(runtime, () => events.push("draw-a"), { key: "a:partial", ready: true });
  assert.deepEqual(events, ["draw-a", "a:partial"]);
  assert.equal(canvas.style.visibility, "visible");

  presentation.draw(runtime, () => events.push("draw-old"), { key: "a:complete", ready: false });
  assert.deepEqual(events, ["draw-a", "a:partial", "draw-old"], "an unready key does not acknowledge old pixels");
  assert.equal(canvas.style.visibility, "visible", "an existing usable scene stays visible");

  presentation.draw(runtime, () => events.push("draw-complete"), { key: "a:complete", ready: true });
  presentation.draw(runtime, () => events.push("orbit"), { key: "a:complete", ready: true });
  assert.deepEqual(events, ["draw-a", "a:partial", "draw-old", "draw-complete", "a:complete", "orbit"]);
});

test("a drawing document can satisfy presentation without mesh or visible ink", () => {
  const canvas = { style: {} }, presented = [];
  const presentation = createFramePresentation({ canvas, renderMode: false, onPresent: (key) => presented.push(key) });
  assert.equal(presentation.draw(
    { hasVisibleModel: false, hasDrawingDocument: true },
    () => {},
    { key: "drawing:complete", ready: true },
  ), true);
  assert.deepEqual(presented, ["drawing:complete"]);
  assert.equal(canvas.style.visibility, "visible");
  assert.equal(presentation.draw(
    { hasVisibleModel: false, hasDrawingDocument: true },
    () => {},
    { key: "empty-drawing:complete", ready: true },
  ), true, "a valid blank drawing still completes opening");
  assert.deepEqual(presented, ["drawing:complete", "empty-drawing:complete"]);
});

test("a failed draw never uncovers the uninitialized canvas", () => {
  const canvas = { style: {} };
  const presentation = createFramePresentation({ canvas, renderMode: true, onPresent: () => assert.fail("not drawn") });
  assert.throws(() => presentation.draw(
    { hasVisibleModel: true, environmentReady: true },
    () => { throw Error("draw failed"); },
    { key: "part:complete", ready: true },
  ));
  assert.equal(canvas.style.visibility, "hidden");
});

test("transition colors follow the destination studio, including custom and transparent backdrops", () => {
  for (const transparent of [false, true]) {
    const style = viewerTransitionBackdrop({ renderMode: true, renderConfiguration: { backdrop: { color: "#103040", transparent } }, viewerTheme: { sceneBackground: "#ffffff" } });
    assert.equal(style.backgroundColor, "#103040");
    assert.equal(style.color, "#e2e8f0");
  }
  assert.equal(viewerTransitionBackdrop({ renderMode: true, renderConfiguration: { backdrop: { color: "#e7e7e5" } } }).color, "#334155");
  assert.equal(viewerTransitionBackdrop({ renderMode: false, background: { solidColor: "#f1f5f9" } }).backgroundColor, "#f1f5f9");
});
