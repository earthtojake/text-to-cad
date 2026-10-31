import assert from "node:assert/strict";
import test from "node:test";

import * as THREE from "three";
import { Line2 } from "three/examples/jsm/lines/Line2.js";
import { LineGeometry } from "three/examples/jsm/lines/LineGeometry.js";
import { LineMaterial } from "three/examples/jsm/lines/LineMaterial.js";
import { annotationMarkObject, normalizeAnnotation } from "./annotation.js";

const stroke = (fields = {}) => ({ id: "1", kind: "stroke", points: [0, 0, 0, 1, 1, 1], color: "#ff2d55", width: 2, ...fields });

test("an annotation file is read with each mark's defaults filled", () => {
  const annotation = normalizeAnnotation({
    units: "mm",
    marks: [
      stroke({ view: "view 1", widths: [1, 0.5], group: "g1", touches: [{ part: "o1.2", ref: "@cad[a.step#f3]" }, { part: "o1.3" }] }),
      { id: "2", kind: "area", points: [0, 0, 0, 1, 0, 0, 1, 1, 0], triangles: [0, 1, 2], color: "#007AFF", opacity: 0.5 },
      { id: "3", kind: "text", points: [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0], color: "#000000", text: "M6", fontPx: 20 },
    ],
  });
  assert.deepEqual(annotation.marks.map(mark => mark.kind), ["stroke", "area", "text"]);
  assert.deepEqual([annotation.marks[0].closed, annotation.marks[0].widths], [false, [1, 0.5]]);
  assert.deepEqual(annotation.marks[0].touches, [{ part: "o1.2", ref: "@cad[a.step#f3]" }, { part: "o1.3" }], "what it touches: a face or edge where named");
  assert.equal(annotation.marks[1].outline, 3, "an area's outline is all its points unless it says otherwise");
  assert.equal(normalizeAnnotation({ marks: [] }).units, "mm");
});

test("an annotation that is not one is refused by what is wrong, an unknown field included", () => {
  for (const [raw, said] of [
    [[], "an annotation is an object"],
    [{ marks: [], colour: "red" }, 'unknown field "colour"'],
    [{ marks: {} }, "marks must be an array"],
    [{ marks: [stroke({ shade: 1 })] }, 'marks[0]: unknown field "shade"'],
    [{ marks: [stroke(), stroke()] }, "marks[1].id must be a unique"],
    [{ marks: [stroke({ kind: "blob" })] }, "marks[0].kind must be one of stroke, area, text"],
    [{ marks: [stroke({ color: "red" })] }, "marks[0].color must be a #rrggbb colour"],
    [{ marks: [stroke({ points: [0, 0] })] }, "marks[0].points must be x, y, z triples"],
    [{ marks: [stroke({ points: [0, 0, 0] })] }, "a stroke has at least two points"],
    [{ marks: [stroke({ width: 0 })] }, "marks[0].width must be a positive number"],
    [{ marks: [stroke({ touches: [{ part: "o1.2", ref: 3 }] })] }, "marks[0].touches must list { part, ref? } entries"],
    [{ parts: {}, marks: [] }, 'unknown field "parts"'],
    [{ marks: [stroke({ dash: "solid" })] }, 'marks[0]: unknown field "dash"'],
    [{ marks: [stroke({ part: "o1.2" })] }, 'marks[0]: unknown field "part"'],
    [{ marks: [stroke({ placement: "surface" })] }, 'marks[0]: unknown field "placement"'],
    [{ marks: [{ ...stroke(), kind: "area", triangles: [0, 1, 5] }] }, "marks[0].triangles must index its points"],
    [{ marks: [{ ...stroke(), kind: "text", fontPx: 12 }] }, "a text mark's points are its four corners"],
  ]) {
    assert.throws(() => normalizeAnnotation(raw), (error) => error.message.startsWith("annotation: ") && error.message.includes(said), said);
  }
});

test("a translucent stroke (the highlighter's) draws once-only, on stencil references of its own; an opaque one is left alone", () => {
  const context = { THREE, Line2, LineGeometry, LineMaterial };
  const stroke = (id, opacity) => ({ id, kind: "stroke", points: [0, 0, 0, 1, 0, 0, 2, 1, 0], color: "#ff2d55", width: 10, opacity });
  const [a, b] = ["a", "b"].map(id => annotationMarkObject(context, stroke(id, 0.35), { lineScale: 1 }));
  const opaque = annotationMarkObject(context, stroke("c", 1), { lineScale: 1 });
  const hidden = object => object.children.find(child => child.userData.annotationHidden);
  for (const object of [a, hidden(a), b, hidden(b)]) {
    assert.equal(object.material.stencilWrite, true);
    assert.equal(object.material.stencilFunc, THREE.NotEqualStencilFunc);
    assert.equal(object.material.stencilZPass, THREE.ReplaceStencilOp);
  }
  // Each stroke and each hidden part its own reference: a crossing stroke blends, its own overlaps do not.
  const refs = [a, hidden(a), b, hidden(b)].map(object => object.material.stencilRef);
  assert.equal(new Set(refs).size, 4);
  assert.ok(refs.every(ref => ref > 0 && ref < 256));
  assert.equal(opaque.material.stencilWrite, false);
});
