import assert from "node:assert/strict";
import test from "node:test";

import { STEP_MODEL_ROOT_ID } from "@hardcore/core/lib/step/stepTree.js";
import { nodeCopyText, selectionCopyPayload } from "./stepCopy.js";

const face = { id: "o1.1.f3", selectorType: "face", copyText: "#o1.1.f3" };
const context = (overrides = {}) => ({
  entry: { file: "hinge.step", kind: "assembly", fileRefPrefix: "hinge.step" }, isAssemblyView: true,
  copyReferenceMap: new Map(), referenceMap: new Map([[face.id, face]]), assemblyPartMap: new Map(), displayRoot: null, root: null,
  ...overrides
});

test("a selection copies its faces and its parts as one reference", () => {
  const payload = selectionCopyPayload(context(), { referenceIds: ["o1.1.f3"], partIds: ["o1.2"] });
  assert.equal(payload.copiedCount, 2);
  assert.deepEqual(payload.lines, ["#o1.1.f3,o1.2"]);
});

test("a single part's root copies as the whole file", () => {
  const payload = selectionCopyPayload(context({ isAssemblyView: false, entry: { file: "block.step", kind: "part" } }),
    { referenceIds: [], partIds: [STEP_MODEL_ROOT_ID] });
  assert.deepEqual(payload.lines, ["#"], "the whole document, which Copy then prefixes with its file");
});

test("one node copies the way the Copy Reference button does: canonical, with the file's prefix", () => {
  assert.equal(nodeCopyText(context(), "o1.1.f3", { topology: true }), "hinge.step#o1.1.f3");
  assert.equal(nodeCopyText(context(), "o1.2"), "hinge.step#o1.2");
  assert.equal(nodeCopyText(context({ entry: { file: "hinge.step", kind: "assembly" } }), "o1.2"), "#o1.2", "no prefix, the bare ref");
  assert.equal(nodeCopyText(context(), "  "), "");
});
