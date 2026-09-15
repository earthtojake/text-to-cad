import assert from "node:assert/strict";
import test from "node:test";
import { flattenVisibleStepTreeRows } from "cadgen-js/lib/step/stepTree.js";
import {
  STEP_TREE_OVERSCAN,
  STEP_TREE_ROW_HEIGHT,
  STEP_TREE_ROW_STRIDE,
  findFocusableStepTreeRow,
  stepTreeFocusFallback,
  stepTreeRowScrollTop,
  stepTreeSiblingPositions,
  stepTreeWindowIndexes,
  stepTreeWindowRange,
} from "./stepTreeWindow.js";

const largeRoot = {
  id: "root", nodeType: "assembly",
  children: Array.from({ length: 100 }, (_, group) => ({
    id: `group-${group}`, nodeType: "assembly", displayName: `Group ${group}`,
    children: Array.from({ length: 100 }, (_, child) => ({
      id: `part-${group}-${child}`, nodeType: "part", displayName: `Part ${group} ${child}`,
    })),
  })),
};
const expandedIds = largeRoot.children.map((node) => node.id);
const rows = flattenVisibleStepTreeRows(largeRoot, expandedIds, { omitRoot: true });

test("ten thousand tree rows render only the viewport, buffer and two retained interactions", () => {
  assert.equal(rows.length, 10100);
  for (const viewportHeight of [80, 280, 600, 1200]) {
    for (const scrollTop of [0, 14, 4000, 9800 * STEP_TREE_ROW_STRIDE]) {
      const range = stepTreeWindowRange(rows.length, { scrollTop, viewportHeight, listTop: 24 });
      const indexes = stepTreeWindowIndexes(range, rows.length, [0, rows.length - 1]);
      assert.ok(indexes.length <= Math.ceil(viewportHeight / STEP_TREE_ROW_STRIDE) + 1 + STEP_TREE_OVERSCAN * 2 + 2);
      assert.ok(indexes.includes(0));
      assert.ok(indexes.includes(rows.length - 1));
      assert.equal(new Set(indexes).size, indexes.length);
      assert.deepEqual(indexes, [...indexes].sort((a, b) => a - b));
      const firstVisible = Math.max(0, Math.floor((scrollTop - 24) / STEP_TREE_ROW_STRIDE));
      assert.ok(indexes.includes(firstVisible));
    }
  }
  assert.equal(stepTreeWindowIndexes({ start: 0, end: 4 }, 10100, [7000, 8000, 9000]).length, 6);
});

test("scroll positioning reveals offscreen picks, keyboard destinations and topology centers", () => {
  const metrics = { scrollTop: 100, viewportHeight: 300, listTop: 24 };
  assert.equal(stepTreeRowScrollTop(9, metrics), 100, "an already visible row must not move");
  assert.equal(stepTreeRowScrollTop(0, metrics), 0);
  for (const block of ["nearest", "center"]) {
    const scrollTop = stepTreeRowScrollTop(9999, metrics, { block });
    const range = stepTreeWindowRange(rows.length, { ...metrics, scrollTop });
    assert.ok(range.start <= 9999 && range.end > 9999);
    const top = metrics.listTop + 9999 * STEP_TREE_ROW_STRIDE;
    assert.ok(top >= scrollTop && top + STEP_TREE_ROW_HEIGHT <= scrollTop + metrics.viewportHeight);
  }
  const tiny = { scrollTop: 400, viewportHeight: 40, listTop: 24 };
  const tinyScrollTop = stepTreeRowScrollTop(12, tiny);
  assert.ok(24 + 12 * STEP_TREE_ROW_STRIDE + STEP_TREE_ROW_HEIGHT <= tinyScrollTop + 40);
});

test("keyboard navigation searches unmounted rows and skips disabled rows in both directions", () => {
  const disabled = (row) => !row.id.endsWith("-99");
  assert.equal(rows[findFocusableStepTreeRow(rows, 0, 1, disabled)].id, "part-0-99");
  assert.equal(rows[findFocusableStepTreeRow(rows, rows.length - 1, -1, disabled)].id, "part-99-99");
  assert.equal(findFocusableStepTreeRow(rows, 50, 1, () => true), -1);
  assert.equal(findFocusableStepTreeRow([], 0, 1, () => false), -1);
});

test("collapse and filtered search preserve logical order, indentation and sibling accessibility", () => {
  const collapsed = flattenVisibleStepTreeRows(largeRoot, [], { omitRoot: true });
  assert.equal(collapsed.length, 100);
  assert.ok(collapsed.every((row) => row.depth === 0));
  const collapsedRange = stepTreeWindowRange(collapsed.length, { scrollTop: 290000, viewportHeight: 600 });
  assert.ok(stepTreeWindowIndexes(collapsedRange, collapsed.length).every((index) => index < 100));

  const filtered = flattenVisibleStepTreeRows(largeRoot, [], { omitRoot: true, query: "part-73-" });
  assert.equal(filtered.length, 101);
  assert.equal(filtered[0].id, "group-73");
  assert.equal(filtered[100].id, "part-73-99");
  assert.equal(filtered[100].depth, 1);
  const positions = stepTreeSiblingPositions(rows);
  assert.deepEqual(positions[0], { position: 1, size: 100 });
  assert.deepEqual(positions[1], { position: 1, size: 100 });
  assert.deepEqual(positions[100], { position: 100, size: 100 });
  assert.deepEqual(positions[101], { position: 2, size: 100 });
  assert.deepEqual(positions[102], { position: 1, size: 100 });
  assert.deepEqual(stepTreeSiblingPositions(filtered)[0], { position: 1, size: 1 });
});

test("a zero-row or not-yet-measured viewport stays bounded", () => {
  assert.deepEqual(stepTreeWindowIndexes(stepTreeWindowRange(0), 0, [0, 10]), []);
  assert.ok(stepTreeWindowIndexes(stepTreeWindowRange(rows.length, { viewportHeight: 0 }), rows.length).length <= STEP_TREE_OVERSCAN);
});

test("collapsing or filtering a focused subtree finds its surviving parent or nearest row", () => {
  const collapsed = flattenVisibleStepTreeRows(largeRoot, [], { omitRoot: true });
  assert.equal(stepTreeFocusFallback(rows, collapsed, "part-73-18"), 73);
  const filtered = collapsed.filter((row) => row.id === "group-7");
  assert.equal(stepTreeFocusFallback(rows, filtered, "part-73-18"), 0);
  assert.equal(stepTreeFocusFallback(rows, [], "part-73-18"), -1);
});
