import assert from "node:assert/strict";
import test from "node:test";

import { VIEWER_PICK_MODE } from "cadjs/lib/viewer/constants.js";
import { viewerPickModeForRenderPane } from "./viewerPickMode.js";

test("viewer pick mode uses assembly picking for unfocused assembly navigation", () => {
  assert.equal(
    viewerPickModeForRenderPane({ viewerMode: "assembly" }),
    VIEWER_PICK_MODE.ASSEMBLY
  );
});

test("viewer pick mode switches focused assemblies to topology picking", () => {
  assert.equal(
    viewerPickModeForRenderPane({
      viewerMode: "assembly",
      focusedPartIds: "o1.4"
    }),
    VIEWER_PICK_MODE.AUTO
  );
});

test("viewer pick mode switches multi-focused assemblies to topology picking", () => {
  assert.equal(
    viewerPickModeForRenderPane({
      viewerMode: "assembly",
      focusedPartIds: ["o1.4", "o1.5"]
    }),
    VIEWER_PICK_MODE.AUTO
  );
});

test("viewer pick mode disables picking while topology assets are pending", () => {
  assert.equal(
    viewerPickModeForRenderPane({
      viewerMode: "assembly",
      focusedPartIds: "o1.4",
      topologySelectionPending: true
    }),
    VIEWER_PICK_MODE.NONE
  );
});
