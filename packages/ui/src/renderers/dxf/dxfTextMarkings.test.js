import assert from "node:assert/strict";
import test from "node:test";
import * as THREE from "three";

import { createDxfTextMarkings } from "./dxfTextMarkings.js";

// A canvas stand-in: enough of the 2D context for the label painter, and a count of how
// many canvases were ever made — which is the whole point of the cache.
function stubCanvas() {
  let made = 0;
  const context = { font: "", fillStyle: "", textBaseline: "", measureText: text => ({ width: text.length * 30 }), fillText() {} };
  globalThis.document = { createElement() { made += 1; return { width: 0, height: 0, getContext: () => context }; } };
  return { made: () => made, restore: () => { delete globalThis.document; } };
}

const place = (marking, size) => ({ position: [marking.position[0], marking.position[1], size.height], basis: new THREE.Matrix4() });
const marking = (value, position, colorHex = "#8a93a3", heightMm = 3) => ({ value, position, colorHex, heightMm, rotationDeg: 0 });

test("a label's canvas is painted once and kept: re-placing it repaints nothing", () => {
  const canvas = stubCanvas();
  try {
    const texts = createDxfTextMarkings(THREE);
    texts.update([marking("PART A", [0, 0]), marking("PART B", [10, 0])], place);
    assert.equal(canvas.made(), 2);
    assert.deepEqual(texts.group.children.map(mesh => mesh.position.x), [0, 10]);
    // What a thickness tick does: the same labels, somewhere else.
    texts.update([marking("PART A", [5, 5]), marking("PART B", [15, 5])], place);
    assert.equal(canvas.made(), 2, "no canvas is repainted for a move");
    assert.deepEqual(texts.group.children.map(mesh => mesh.position.x), [5, 15]);
    // Changing what a label SAYS, or its colour, is a new canvas.
    texts.update([marking("PART C", [0, 0]), marking("PART B", [10, 0], "#ff0000")], place);
    assert.equal(canvas.made(), 4);
    texts.dispose();
  } finally { canvas.restore(); }
});

test("a label that drops out hides its plane; a blank one is never drawn", () => {
  const canvas = stubCanvas();
  try {
    const texts = createDxfTextMarkings(THREE);
    texts.update([marking("A", [0, 0]), marking("B", [1, 0])], place);
    assert.deepEqual(texts.group.children.map(mesh => mesh.visible), [true, true]);
    texts.update([marking("A", [0, 0]), marking("   ", [1, 0])], place);
    assert.deepEqual(texts.group.children.map(mesh => mesh.visible), [true, false]);
    assert.equal(canvas.made(), 2, "a blank label paints nothing");
    texts.dispose();
  } finally { canvas.restore(); }
});

test("without a canvas — a headless build — a drawing simply has no labels", () => {
  const texts = createDxfTextMarkings(THREE);
  assert.doesNotThrow(() => texts.update([marking("A", [0, 0])], place));
  assert.deepEqual(texts.group.children, []);
  texts.dispose();
});

test("dispose releases every canvas texture, its material and its geometry", () => {
  const canvas = stubCanvas();
  try {
    const texts = createDxfTextMarkings(THREE);
    texts.update([marking("A", [0, 0]), marking("B", [1, 0])], place);
    const released = [];
    for (const mesh of texts.group.children) {
      mesh.geometry.dispose = () => released.push("geometry");
      mesh.material.map.dispose = () => released.push("texture");
      mesh.material.dispose = () => released.push("material");
    }
    texts.dispose();
    assert.deepEqual(released.sort(), ["geometry", "geometry", "material", "material", "texture", "texture"]);
    assert.deepEqual(texts.group.children, []);
  } finally { canvas.restore(); }
});
