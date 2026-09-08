// Where the open panel is drawn: the host's slot when it gives one, the
// surface's own column when it does not. The standalone viewer passes
// nothing, so "nothing" must keep meaning "draw the column".
import assert from "node:assert/strict";
import test from "node:test";

import { normalizeHostPanelSlot, resolveHostPanelPlacement } from "./hostPanelSlot.js";

test("only an element node is a slot", () => {
  const element = { nodeType: 1 };
  assert.equal(normalizeHostPanelSlot(element), element);
  // A ref that has not attached yet, and the standalone case.
  assert.equal(normalizeHostPanelSlot(null), null);
  assert.equal(normalizeHostPanelSlot(undefined), null);
  // A text node, a fragment, a selector and a number are not boxes.
  assert.equal(normalizeHostPanelSlot({ nodeType: 3 }), null);
  assert.equal(normalizeHostPanelSlot({ nodeType: 11 }), null);
  assert.equal(normalizeHostPanelSlot({}), null);
  assert.equal(normalizeHostPanelSlot("#panel"), null);
  assert.equal(normalizeHostPanelSlot(1), null);
});

test("a slot is rendered into; without one the surface draws its own column", () => {
  const element = { nodeType: 1 };
  assert.deepEqual(resolveHostPanelPlacement(element), { slot: element, drawsOwnColumn: false });
  assert.deepEqual(resolveHostPanelPlacement(null), { slot: null, drawsOwnColumn: true });
  assert.deepEqual(resolveHostPanelPlacement(undefined), { slot: null, drawsOwnColumn: true });
  // Never both: a panel portaled out must not also reserve a column.
  for (const value of [element, null, undefined, {}, "#panel"]) {
    const placement = resolveHostPanelPlacement(value);
    assert.equal(placement.drawsOwnColumn, placement.slot === null);
  }
});
