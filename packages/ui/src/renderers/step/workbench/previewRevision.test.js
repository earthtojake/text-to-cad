import assert from "node:assert/strict";
import test from "node:test";
import { bendsATube, createPreviewPartsGate, previewRevisionEntry } from "./previewRevision.js";

const TREE = "p".repeat(64);
const ANNOTATIONS = "a".repeat(64);
const FILE = "/models/hinge_block.step";
const URL = `/__cad/store?file=${TREE}&producer=%7B%7D`;
const preview = (extra = {}) => ({ tree: TREE, producer: {}, parts: {}, complete: false, annotations: null, ...extra });
const view = { kind: "assembly-package", entryKind: "assembly", tree: TREE };
const articulation = { controls: [{ id: "hinge", min: 0, max: 90 }], poses: {} };
const swing = { clips: [{ id: "swing", tracks: [{ targets: ["o:5da881c8dcfe"], times: [0, 1] }] }] };
const display = { "o:5da881c8dcfe": { finish: "brushed" } };
// The catalog's entry on screen when the build began: the saved file, with its sidecar resolved.
const inHand = { file: FILE, kind: "assembly", url: "/__cad/store?file=saved", hash: "s".repeat(64), documentHash: "d".repeat(64),
  articulation, poseUrl: "/models/hinge_block.step.json?v=3", animation: swing, display, appearanceHash: "e".repeat(64) };

test("the preview is an entry read as a saved file's row is, and never the catalog's entry", () => {
  const entry = previewRevisionEntry({ file: FILE, preview: preview(), view, url: URL });
  assert.deepEqual(entry, { file: FILE, kind: "assembly", url: URL, hash: TREE, preview: true });
  assert.equal(previewRevisionEntry({ file: FILE, preview: preview(), view: { ...view, entryKind: "part" }, url: URL }).kind, "part");
  // Nothing of the file: no document hash, no sidecar URL, nothing until the view is read.
  assert.equal(entry.documentHash, undefined);
  assert.equal(previewRevisionEntry({ file: FILE, preview: preview(), view: null, url: URL }), null);
  assert.equal(previewRevisionEntry({ file: FILE, preview: null, view, url: URL }), null);
});

test("what is in hand stays in hand while the build may still resolve its own, by the tokens the two share", () => {
  const pending = previewRevisionEntry({ file: FILE, preview: preview(), view, url: URL, inHand, pending: true });
  assert.equal(pending.articulation, articulation);
  assert.equal(pending.poseUrl, inHand.poseUrl);
  assert.equal(pending.animation, swing);
  assert.equal(pending.display, display);
  assert.equal(pending.appearanceHash, inHand.appearanceHash);
  assert.equal(pending.hash, TREE, "the geometry is the preview's");
  // Once the build has ended with nothing named, there is nothing to carry.
  const ended = previewRevisionEntry({ file: FILE, preview: preview(), view, url: URL, inHand, pending: false });
  assert.deepEqual(Object.keys(ended).sort(), ["file", "hash", "kind", "preview", "url"]);
  // Another file's entry, or one with no mesh, is nothing in hand.
  const other = previewRevisionEntry({ file: FILE, preview: preview(), view, url: URL, inHand: { ...inHand, file: "/models/other.step" }, pending: true });
  assert.equal(other.articulation, undefined);
  assert.equal(previewRevisionEntry({ file: FILE, preview: preview(), view, url: URL, inHand: { ...inHand, hash: "" }, pending: true }).display, undefined);
});

test("the preview's annotations bind its articulation, routines and finishes as a saved file's row carries them", () => {
  const named = preview({ annotations: ANNOTATIONS });
  const annotations = { kind: "preview-annotations", schemaVersion: 1, tree: TREE, articulation, appearance: { materials: {} }, display, animation: swing };
  const bound = previewRevisionEntry({ file: FILE, preview: named, view, url: URL, annotations, inHand: null, pending: true });
  assert.equal(bound.articulation, articulation);
  assert.equal(bound.poseUrl, `preview:${ANNOTATIONS}`, "versioned by the object it came in");
  assert.equal(bound.animation, swing);
  assert.equal(bound.display, display);
  assert.equal(bound.appearanceHash, `preview:${ANNOTATIONS}`);
  // A model declaring nothing binds nothing, and no longer carries what was in hand.
  const none = previewRevisionEntry({ file: FILE, preview: named, view, url: URL, inHand, pending: true,
    annotations: { ...annotations, articulation: null, appearance: null, display: null, animation: null } });
  assert.deepEqual(Object.keys(none).sort(), ["file", "hash", "kind", "preview", "url"]);
  // Finishes the same as the ones in hand keep their token, so the composition on screen stays.
  const same = previewRevisionEntry({ file: FILE, preview: named, view, url: URL, annotations, inHand, pending: true });
  assert.equal(same.appearanceHash, inHand.appearanceHash);
  const changed = previewRevisionEntry({ file: FILE, preview: named, view, url: URL, inHand, pending: true,
    annotations: { ...annotations, display: { "o:5da881c8dcfe": { finish: "matte" } } } });
  assert.equal(changed.appearanceHash, `preview:${ANNOTATIONS}`);
  // Declared appearance that resolves to no occurrence is still the preview's own: an empty table.
  assert.deepEqual(previewRevisionEntry({ file: FILE, preview: named, view, url: URL, annotations: { ...annotations, display: null } }).display, {});
});

test("finishes wait for the preview's geometry to be whole on screen; motion never does", () => {
  const named = preview({ annotations: ANNOTATIONS });
  const annotations = { tree: TREE, articulation, appearance: {}, display: { "o:5da881c8dcfe": { finish: "matte" } }, animation: null };
  const undressed = previewRevisionEntry({ file: FILE, preview: named, view, url: URL, annotations, inHand, pending: true, dressed: false });
  assert.equal(undressed.articulation, articulation, "the pose binds at once");
  assert.equal(undressed.display, display, "the finishes in hand stay until the geometry is whole");
  assert.equal(undressed.appearanceHash, inHand.appearanceHash);
  const dressed = previewRevisionEntry({ file: FILE, preview: named, view, url: URL, annotations, inHand, pending: true, dressed: true });
  assert.deepEqual(dressed.display, annotations.display);
});

test("a routine that bends a tube plays on a preview only as the one in hand, with the saved document's skins", () => {
  const bending = { clips: [{ id: "flex", tracks: [{ targets: ["o:1"], times: [0, 1], tube: { radius: 1 } }] }] };
  assert.equal(bendsATube(bending), true);
  assert.equal(bendsATube(swing), false);
  const named = preview({ annotations: ANNOTATIONS });
  const annotations = { tree: TREE, articulation: null, appearance: null, display: null, animation: bending };
  const skinned = { ...inHand, animation: JSON.parse(JSON.stringify(bending)), tubeSkinsUrl: "/__cad/skins?document=d" };
  const kept = previewRevisionEntry({ file: FILE, preview: named, view, url: URL, annotations, inHand: skinned });
  assert.equal(kept.animation, skinned.animation);
  assert.equal(kept.tubeSkinsUrl, skinned.tubeSkinsUrl);
  // Changed keyframes, or no skins in hand: the routine waits for the save.
  const changed = previewRevisionEntry({ file: FILE, preview: named, view, url: URL, annotations, inHand: { ...skinned, animation: swing } });
  assert.equal(changed.animation, undefined);
  assert.equal(previewRevisionEntry({ file: FILE, preview: named, view, url: URL, annotations, inHand }).animation, undefined);
});

test("the parts gate waits for a part until the feed names it, or until the build has named all it can", async () => {
  const gate = createPreviewPartsGate(TREE);
  assert.equal(gate.has("c2"), false);
  gate.update({ c1: "part-one" }, false);
  assert.equal(gate.has("c1"), true);
  let namedC2 = false, namedC3 = false;
  const waitC2 = gate.whenNamed("c2").then(() => { namedC2 = true; });
  const waitC3 = gate.whenNamed("c3").then(() => { namedC3 = true; });
  await Promise.resolve();
  assert.deepEqual([namedC2, namedC3], [false, false]);
  gate.update({ c1: "part-one", c2: "part-two" }, false);
  await waitC2;
  assert.deepEqual([namedC2, namedC3], [true, false]);
  gate.update({ c1: "part-one", c2: "part-two" }, true);
  await waitC3;
  assert.equal(gate.has("c3"), false, "named all it can: the rest are a saved file's missing parts");
  assert.equal(gate.complete, true);
  await gate.whenNamed("c1");
  // A load abandoned while it waits is abandoned: its wait rejects with an AbortError.
  const controller = new AbortController();
  const later = createPreviewPartsGate(TREE);
  const abandoned = later.whenNamed("c9", controller.signal);
  controller.abort();
  await assert.rejects(abandoned, { name: "AbortError" });
  await assert.rejects(later.whenNamed("c9", controller.signal), { name: "AbortError" });
});
