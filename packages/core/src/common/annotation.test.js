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

test("a file the page wrote before reads exactly as it did", () => {
  const corners = [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0];
  const written = { units: "mm", marks: [
    { id: "ink-1", kind: "stroke", points: [0, 0, 0, 1, 1, 1], color: "#ff2d55", width: 2, opacity: 1, closed: false, view: "view 1", widths: [1, 0.5],
      touches: [{ part: "i130", ref: "a.step#f3" }, { part: "i9" }] },
    { id: "ink-2", kind: "area", points: [0, 0, 0, 1, 0, 0, 1, 1, 0, 0.5, 0.5, 0], outline: 3, triangles: [0, 1, 3, 1, 2, 3], color: "#007aff", opacity: 0.5 },
    { id: "ink-3", kind: "text", points: corners, color: "#000000", text: "M6", fontPx: 20, group: "g" },
  ] };
  assert.deepEqual(normalizeAnnotation(written), { units: "mm", marks: [
    { id: "ink-1", kind: "stroke", points: [0, 0, 0, 1, 1, 1], color: "#ff2d55", view: "view 1", opacity: 1, width: 2, widths: [1, 0.5], closed: false,
      touches: [{ part: "i130", ref: "a.step#f3" }, { part: "i9" }] },
    { id: "ink-2", kind: "area", points: [0, 0, 0, 1, 0, 0, 1, 1, 0, 0.5, 0.5, 0], color: "#007aff", opacity: 0.5, triangles: [0, 1, 3, 1, 2, 3], outline: 3 },
    { id: "ink-3", kind: "text", points: corners, color: "#000000", text: "M6", fontPx: 20, group: "g" },
  ] });
});

test("a Quick Edit's packet reads shortened: a mark with no id takes one by its place, what it touches may be selectors, an area may be its outline", () => {
  const annotation = normalizeAnnotation({ units: "mm", marks: [
    { kind: "stroke", points: [0, 0, 0, 1, 1, 1], color: "#ff2d55", width: 2, view: "view 1",
      touches: ["head_shell/f:build_head.helmet~5df450b1dd03", { part: "i3", ref: "a.step#f3" }] },
    stroke({ id: "mark 1" }),
    { kind: "area", points: [0, 0, 0, 4, 0, 0, 4, 4, 0, 0, 4, 0], color: "#00aa44", opacity: 0.4 },
    { kind: "text", points: [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0], color: "#000000", text: "M6", fontPx: 20 },
  ] });
  // Each mark its own id, by its place, and never another mark's.
  assert.deepEqual(annotation.marks.map(mark => mark.id), ["mark 1.2", "mark 1", "mark 3", "mark 4"]);
  // A mark that says nothing of them is opaque, and a stroke open.
  assert.deepEqual([annotation.marks[0].opacity ?? 1, annotation.marks[0].closed], [1, false]);
  // What it touches, as selectors in the file or as the page's own entries, each as it was given.
  assert.deepEqual(annotation.marks[0].touches, ["head_shell/f:build_head.helmet~5df450b1dd03", { part: "i3", ref: "a.step#f3" }]);
  // An area with no triangles is its outline alone: every one of its points.
  assert.deepEqual([annotation.marks[2].outline, "triangles" in annotation.marks[2], annotation.marks[2].opacity], [4, false, 0.4]);
  // What is still no annotation: an empty id, an empty selector, an outline of two points.
  assert.throws(() => normalizeAnnotation({ marks: [stroke({ id: "" })] }), /marks\[0\]\.id must be a unique/);
  assert.throws(() => normalizeAnnotation({ marks: [stroke({ touches: [""] })] }), /marks\[0\]\.touches must list/);
  assert.throws(() => normalizeAnnotation({ marks: [{ kind: "area", points: [0, 0, 0, 1, 0, 0], color: "#00aa44" }] }), /marks\[0\]\.outline must count/);
});

test("an area with no triangles is drawn as its outline: a closed line, 1.5 pixels at the viewer's height, as cad's stills draw every area", () => {
  const context = { THREE, Line2, LineGeometry, LineMaterial };
  const [ring] = normalizeAnnotation({ marks: [{ kind: "area", points: [0, 0, 0, 4, 0, 0, 4, 4, 0, 0, 4, 0], color: "#00aa44" }] }).marks;
  const object = annotationMarkObject(context, ring, { lineScale: 2 });
  assert.deepEqual([object.isLine2, object.material.linewidth], [true, 3]);
  // Its four sides, the last back to where it started.
  const ends = object.geometry.attributes.instanceEnd;
  assert.equal(ends.count, 4);
  assert.deepEqual([ends.getX(3), ends.getY(3), ends.getZ(3)], [0, 0, 0]);
  // Faint where the model hides it, as every mark is.
  assert.ok(object.children.some(child => child.userData.annotationHidden));
  // An area with its triangles is still their fill.
  const [fill] = normalizeAnnotation({ marks: [{ id: "a", kind: "area", points: [0, 0, 0, 1, 0, 0, 1, 1, 0], triangles: [0, 1, 2], color: "#00aa44" }] }).marks;
  assert.equal(annotationMarkObject(context, fill, { lineScale: 2 }).isMesh, true);
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
