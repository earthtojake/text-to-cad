import assert from "node:assert/strict";
import test from "node:test";
import { goneFromEngine, openingProgress } from "./useXbfScene.js";

test("a STEP opened as a file starts on its import's first stage, the engine's own event; any other document is a read", () => {
  for (const [file, job] of [["/work/tom.step", "tom.step"], ["/work/TOM.STP", "TOM.STP"], ["/work/tom.step?v=2", "tom.step"], ["C:\\work\\tom.step", "tom.step"]]) {
    assert.deepEqual(openingProgress(file), { kind: "import", stage: "read", job, outputs: [], detail: "", done: 0, total: null, elapsedMs: 0 });
  }
  for (const file of ["/work/juno.xbf", "8c1f5a0e-1d3b-5d6e-9a7f-2b4c6d8e0f12", ""]) {
    assert.deepEqual(openingProgress(file), { phase: "read", label: "Opening document", done: 0, total: 0, determinate: false });
  }
});

test("only a document the engine no longer holds is opened again: not a lost connection, not a refusal", () => {
  assert.equal(goneFromEngine(Object.assign(new Error("the document's version: the engine answered 404"), { status: 404 })), true);
  assert.equal(goneFromEngine(Object.assign(new Error("the engine answered 500"), { status: 500 })), false);
  assert.equal(goneFromEngine(new TypeError("Failed to fetch")), false);
  assert.equal(goneFromEngine(null), false);
});
