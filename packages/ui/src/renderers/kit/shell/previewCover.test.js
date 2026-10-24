import assert from "node:assert/strict";
import test from "node:test";
import { previewCoverStep } from "./previewCover.js";

test("new components restart the picture and wait for convergence", () => {
  // A published component landed: the picture fell from sample 9 back to 1. Nothing moves the view.
  assert.equal(previewCoverStep({ presented: true, loading: false, moving: false, progress: { sample: 1, samples: 32 } }), "converge");
  assert.equal(previewCoverStep({ presented: true, loading: false, moving: false, progress: { sample: 32, samples: 32 } }), "lift");
  // An orbit or a routine starts the picture every frame: there is nothing to wait for.
  assert.equal(previewCoverStep({ presented: true, loading: false, moving: true, progress: { sample: 0, samples: 32 } }), "lift");
  // A view that draws no studio frame (lighting off, software WebGL) lifts once it has presented.
  assert.equal(previewCoverStep({ presented: true, loading: false, moving: false, progress: null }), "lift");
});

test("the cover waits for Preview's first frame and for the complete published geometry", () => {
  assert.equal(previewCoverStep({ presented: false, loading: false, moving: true, progress: null }), "wait");
  assert.equal(previewCoverStep({ presented: true, loading: true, moving: false, progress: { sample: 32, samples: 32 } }), "wait");

});
