import assert from "node:assert/strict";
import test from "node:test";
import { annotationAnchor, annotationDelivered, annotationReferenceLabel, createAnnotation, readAnnotations } from "./stepAnnotations.js";

const anchor = { point: [1, 2, 3], normal: null };

test("a chip names a face, edge or vertex by its number, a part by its name, and counts a group", () => {
  assert.equal(annotationReferenceLabel("o1.1.e3"), "Edge 3");
  assert.equal(annotationReferenceLabel("o1.2.f12"), "Face 12");
  assert.equal(annotationReferenceLabel("o1.v4"), "Vertex 4");
  assert.equal(annotationReferenceLabel("o1.2", "Arm"), "Arm");
  assert.equal(annotationReferenceLabel("o1.1.f2,o1.1.f5"), "2 faces");
  assert.equal(annotationReferenceLabel("o1.1.f2,f5"), "2 faces", "the shorthand group form");
  assert.equal(annotationReferenceLabel("o1.1.f2,o1.1.e5"), "2 references");
  assert.equal(annotationReferenceLabel("o1.2"), "o1.2");
  assert.equal(annotationReferenceLabel(""), "Whole model");
});

test("an annotation needs something to be pinned to and somewhere to sit", () => {
  assert.equal(createAnnotation([], "make a hole", { anchor }), null);
  assert.equal(createAnnotation([{ selector: "o1.1.e3" }], "make a hole"), null, "no anchor");
  assert.deepEqual(createAnnotation([{ selector: "o1.1.e3" }], "make a hole in it", { id: "a1", anchor }),
    { id: "a1", references: [{ selector: "o1.1.e3", label: "Edge 3" }], text: "make a hole in it", anchor });
  assert.deepEqual(createAnnotation([{ selector: "" }], "make it lighter", { id: "a2", anchor }).references,
    [{ selector: "", label: "Whole model" }], "the whole model keeps its empty selector");
});

test("a stored list is read forgivingly, with ids unique", () => {
  assert.deepEqual(readAnnotations(null), []);
  assert.deepEqual(readAnnotations([{ id: "x", anchor }, { references: [{ selector: "o1" }], anchor }, "junk"]), []);
  const one = { id: "a1", references: [{ selector: "o1.1.f1" }], text: "x", anchor: { point: [1, 2, 3], normal: "up" } };
  const read = readAnnotations([one, one]);
  assert.equal(read.length, 1);
  assert.deepEqual(read[0].anchor, { point: [1, 2, 3], normal: null });
});

test("only a delivery that reached the chat box keeps an annotation", () => {
  assert.equal(annotationDelivered({ status: "added", partIds: [] }), true);
  assert.equal(annotationDelivered({ status: "copied", partIds: [] }), true);
  assert.equal(annotationDelivered({ status: "failed" }), false);
  assert.equal(annotationDelivered(undefined), false);
});

test("a dot sits in the middle of what the annotation is about", () => {
  assert.equal(annotationAnchor([]), null);
  assert.equal(annotationAnchor([{ selectorType: "edge" }]), null, "nothing to place it on");
  assert.deepEqual(annotationAnchor([{ selectorType: "face", center: [1, 2, 3], normal: [0, 0, 1] }]),
    { point: [1, 2, 3], normal: [0, 0, 1] });
  assert.deepEqual(annotationAnchor([{ selectorType: "occurrence", bbox: { min: [0, 0, 0], max: [2, 4, 6] } }]),
    { point: [1, 2, 3], normal: null });
  assert.deepEqual(annotationAnchor([{ selectorType: "face", center: [0, 0, 0], normal: [1, 0, 0] }, { selectorType: "edge", center: [2, 2, 2] }]),
    { point: [1, 1, 1], normal: null }, "several: the average, and no single normal");
});
