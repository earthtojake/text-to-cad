import assert from "node:assert/strict";
import test from "node:test";
import { initialEditingPreview, reduceEditingPreview, editingPreviewEntry, previewGeometryChanged } from "./editingPreview.js";

test("an empty initial catalog is safe and geometry changes invalidate only the same file", () => {
  assert.equal(previewGeometryChanged(null, {}), false);
  assert.equal(previewGeometryChanged({}, {}), false);
  const prior = { file: "part.step", hash: "saved", preview: false };
  assert.equal(previewGeometryChanged(prior, { ...prior, hash: "preview", preview: true }), true);
  assert.equal(previewGeometryChanged(prior, { ...prior, file: "other.step", hash: "preview", preview: true }), false);
});

const update = (revision, tree, extra = {}) => ({ epoch: "a", revision, output: "/part.step", state: "building",
  ...(tree ? { preview: { tree, url: `/${tree}`, sequence: 1 } } : {}), ...extra });

test("new request preserves visible geometry until its preview arrives and ignores late older results", () => {
  const first = reduceEditingPreview(initialEditingPreview(), update(1, "old"));
  const pending = reduceEditingPreview(first, update(2));
  assert.equal(pending.preview.tree, "old");
  assert.equal(reduceEditingPreview(pending, update(1, "late")), pending);
  const ready = reduceEditingPreview(pending, update(2, "new"));
  assert.equal(ready.preview.tree, "new");
});
test("a daemon epoch change expires preview ordering and failed saves retain the visible model", () => {
  const first = reduceEditingPreview(initialEditingPreview(), update(99, "old"));
  const failed = reduceEditingPreview(first, update(100, null, { state: "failed", error: "Disk full" }));
  assert.equal(failed.preview.tree, "old");
  const restarted = reduceEditingPreview(failed, { ...update(1), epoch: "b" });
  assert.equal(restarted.preview, null);
});
test("active edit updates retain useful phase narration and completed or idle states clear it", () => {
  const building = reduceEditingPreview(initialEditingPreview(), update(7, null, {
    phase: "Building geometry", detail: "finger linkage", updatedAt: 1234,
  }));
  const publication = reduceEditingPreview(building, update(7, "preview-7", {
    phase: "", detail: "", updatedAt: null,
  }));
  assert.equal(publication.phase, "Building geometry");
  assert.equal(publication.detail, "finger linkage");
  assert.equal(publication.updatedAt, 1234);
  const done = reduceEditingPreview(publication, update(7, null, { state: "done" }));
  assert.equal(done.phase, "");
  assert.equal(done.detail, "");
  assert.equal(done.updatedAt, 0);
  const idle = reduceEditingPreview(done, { state: "disconnected" });
  assert.equal(idle.phase, "");
  assert.equal(idle.detail, "");
});
test("a successful save keeps the current authored preview in Follow edits", () => {
  const saved = { tree: "saved-tree", documentHash: "bytes" };
  const state = reduceEditingPreview(initialEditingPreview(), update(1, "preview", { saved }));
  const entry = { file: "/part.step", kind: "assembly", hash: "old", sourceUrl: "/old.json", poseUrl: "/old.json" };
  const render = editingPreviewEntry(state, entry);
  assert.equal(render.sourceSidecar, null);
  assert.equal(render.appearanceHash, "");
  assert.equal(render.hash, "preview");
  assert.equal(render.poseUrl, "");
  assert.equal(entry.hash, "old");
  assert.ok(editingPreviewEntry(state, { ...entry, hash: "saved-tree", documentHash: "other-bytes" }));
  assert.equal(editingPreviewEntry(state, { ...entry, hash: "saved-tree", documentHash: "bytes" }).hash, "preview");
  const pending = reduceEditingPreview(state, update(2));
  assert.equal(editingPreviewEntry(pending, { ...entry, hash: "saved-tree", documentHash: "bytes" }).hash, "preview",
    "the prior visible preview stays while the next revision builds");
  const newPreview = reduceEditingPreview(pending, update(2, "new-preview"));
  assert.equal(editingPreviewEntry(newPreview, { ...entry, hash: "saved-tree", documentHash: "bytes" }).hash, "new-preview");
  assert.equal(editingPreviewEntry(state, { ...entry, file: "relative/part.step" }).file, "relative/part.step");
});

test("editing previews expose appearance and animation metadata independently of geometry", () => {
  const appearance = {
    materials: { metal: { name: "Metal", metalness: 0.9 } },
    assignments: { finger: "metal" }
  };
  const animation = { language: "javascript", source: "export const clips = {};" };
  const state = reduceEditingPreview(initialEditingPreview(), update(8, "same-tree", {
    preview: { tree: "same-tree", url: "/same-tree", sequence: 3, appearance, animation }
  }));
  const entry = editingPreviewEntry(state, { file: "/hand.step", hash: "saved" });
  assert.equal(entry.previewAppearance, appearance);
  assert.equal(entry.previewAnimation, animation);
  assert.equal(entry.appearanceHash, "preview:8:3");
  assert.equal(entry.animationHash, "preview:8:3");
  assert.equal(Object.hasOwn(entry, "renderModuleUrl"), false);
});

test("a successful no-op without a matching current preview falls back to validated saved bytes", () => {
  const entry = { file: "/part.step", kind: "assembly", hash: "saved-1", documentHash: "bytes-1" };
  const first = reduceEditingPreview(initialEditingPreview(), update(1, "preview-1", {
    saved: { tree: "saved-1", documentHash: "bytes-1" },
  }));
  const pending = reduceEditingPreview(first, update(2));
  assert.equal(editingPreviewEntry(pending, entry).hash, "preview-1");
  const noOp = reduceEditingPreview(pending, update(2, null, {
    state: "done",
    saved: { tree: "saved-2", documentHash: "bytes-2" },
  }));
  assert.ok(editingPreviewEntry(noOp, entry), "old catalog cannot replace the visible preview");
  assert.equal(editingPreviewEntry(noOp, { ...entry, hash: "saved-2", documentHash: "bytes-2" }), null);
});

test("missing preview objects fall back only after the current saved catalog is validated", () => {
  const saved = { tree: "saved-tree", documentHash: "bytes" };
  const ready = reduceEditingPreview(initialEditingPreview(), update(3, "preview", { saved }));
  const unavailable = reduceEditingPreview(ready, update(3, null, {
    state: "done",
    saved,
    previewUnavailable: true,
    error: "Preview geometry is no longer available in the cache",
  }));
  assert.equal(unavailable.preview.tree, "preview", "the last loaded preview remains available as a fallback");
  assert.equal(unavailable.previewUnavailable, true);
  assert.ok(editingPreviewEntry(unavailable, { hash: "old", documentHash: "old" }));
  assert.equal(editingPreviewEntry(unavailable, { hash: "saved-tree", documentHash: "bytes" }), null);

  const nextRevision = reduceEditingPreview(unavailable, update(4));
  assert.equal(nextRevision.previewUnavailable, false, "a new revision gets a fresh preview opportunity");
  const restored = reduceEditingPreview(nextRevision, update(4, "preview-4"));
  assert.equal(restored.previewUnavailable, false);
  assert.equal(editingPreviewEntry(restored, { hash: "saved-tree", documentHash: "bytes" }).hash, "preview-4");
});

test("failed saves and stale missing-preview events cannot displace the visible preview", () => {
  const ready = reduceEditingPreview(initialEditingPreview(), update(5, "preview-5"));
  const failed = reduceEditingPreview(ready, update(5, null, { state: "failed", error: "Disk full" }));
  assert.equal(editingPreviewEntry(failed, { hash: "saved", documentHash: "bytes" }).hash, "preview-5");
  const stale = reduceEditingPreview(failed, update(4, null, { previewUnavailable: true }));
  assert.equal(stale, failed);
  assert.equal(stale.previewUnavailable, false);
});

test("an expired failed preview recovers an earlier saved result only from its exact catalog identity", () => {
  const saved = { tree: "saved-1", documentHash: "bytes-1" };
  const entry = { file: "/part.step", hash: saved.tree, documentHash: saved.documentHash };
  const first = reduceEditingPreview(initialEditingPreview(), update(1, "preview-1", { saved }));
  const pending = reduceEditingPreview(first, update(2));
  assert.equal(editingPreviewEntry(pending, entry).hash, "preview-1");
  const next = reduceEditingPreview(pending, update(2, "preview-2"));
  const failed = reduceEditingPreview(next, update(2, null, { state: "failed", error: "Disk full" }));
  assert.equal(failed.saved, null);
  assert.deepEqual(failed.retainedSaved, saved);
  assert.equal(editingPreviewEntry(failed, entry).hash, "preview-2");
  const expired = reduceEditingPreview(failed, update(2, null, {
    state: "failed", error: "Preview geometry is no longer available in the cache", previewUnavailable: true,
  }));
  assert.equal(editingPreviewEntry(expired, { ...entry, hash: "another-tree" }).hash, "preview-2");
  assert.equal(editingPreviewEntry(expired, { ...entry, documentHash: "changed-bytes" }).hash, "preview-2");
  assert.equal(editingPreviewEntry(expired, entry), null);
});
