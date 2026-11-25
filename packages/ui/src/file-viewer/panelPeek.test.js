import assert from "node:assert/strict";
import test from "node:test";

import { PANEL_PEEK_DELAY_MS, PANEL_PEEK_LEAVE_MS, PANEL_PEEK_EXIT_FALLBACK_MS, PANEL_PEEK_IN_CLASS, PANEL_PEEK_IN_MS, PANEL_PEEK_OUT_CLASS, PANEL_PEEK_OUT_MS, PANEL_SHEET_LEFT_CLASS } from "./panelPeek.js";

// The peek's timings, in one place: the classes carry the durations the constants say, and the fallback outlasts the
// slide out (`panelPeek.js`).
test("the peek's slide classes carry its duration constants, and the exit fallback outlasts the slide out", () => {
  assert.deepEqual([PANEL_PEEK_DELAY_MS, PANEL_PEEK_LEAVE_MS, PANEL_PEEK_IN_MS, PANEL_PEEK_OUT_MS], [250, 150, 100, 80]);
  assert.match(PANEL_PEEK_IN_CLASS, new RegExp(`\\bduration-${PANEL_PEEK_IN_MS}\\b.*\\bease-out\\b`));
  assert.match(PANEL_PEEK_OUT_CLASS, new RegExp(`\\bduration-${PANEL_PEEK_OUT_MS}\\b.*\\bease-in\\b`));
  assert.ok(PANEL_PEEK_EXIT_FALLBACK_MS > PANEL_PEEK_OUT_MS);
  // A phone's sheet slides as the peek does.
  assert.match(PANEL_SHEET_LEFT_CLASS, new RegExp(`state=open\\]:duration-${PANEL_PEEK_IN_MS}\\b.*state=closed\\]:duration-${PANEL_PEEK_OUT_MS}\\b`));
});
