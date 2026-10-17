import assert from "node:assert/strict";
import test from "node:test";

import { STEP_MODEL_ROOT_ID } from "@text-to-cad/core/lib/step/stepTree.js";
import { nodeCopyText, selectionCopyPayload } from "./stepCopy.js";

// Occurrence tokens of two parts and a face name of the first: a ref is `<occurrence>/<element>`.
const BASE = "o:3f2a9c1d7e5b";
const ARM = "o:a1b2c3d4e5f6";
const FACE = `${BASE}/f:base.extrude1.3`;
const face = { id: FACE, selectorType: "face", copyText: `#${FACE}` };
const context = (overrides = {}) => ({
  entry: { file: "hinge.step", kind: "assembly", fileRefPrefix: "hinge.step" }, isAssemblyView: true,
  copyReferenceMap: new Map(), referenceMap: new Map([[face.id, face]]), assemblyPartMap: new Map(), displayRoot: null, root: null,
  ...overrides
});

test("a selection copies its faces and its parts as one reference", () => {
  const payload = selectionCopyPayload(context(), { referenceIds: [FACE], partIds: [ARM] });
  assert.equal(payload.copiedCount, 2);
  assert.deepEqual(payload.lines, [`#${FACE},${ARM}`]);
});

test("a single part's root copies as the whole file", () => {
  const payload = selectionCopyPayload(context({ isAssemblyView: false, entry: { file: "block.step", kind: "part" } }),
    { referenceIds: [], partIds: [STEP_MODEL_ROOT_ID] });
  assert.deepEqual(payload.lines, ["#"], "the whole document, which Copy then prefixes with its file");
});

test("one node copies the way the Copy Reference button does: canonical, with the file's prefix", () => {
  assert.equal(nodeCopyText(context(), FACE, { topology: true }), `hinge.step#${FACE}`);
  assert.equal(nodeCopyText(context(), ARM), `hinge.step#${ARM}`);
  assert.equal(nodeCopyText(context({ entry: { file: "hinge.step", kind: "assembly" } }), ARM), `#${ARM}`, "no prefix, the bare ref");
  assert.equal(nodeCopyText(context(), "  "), "");
});
