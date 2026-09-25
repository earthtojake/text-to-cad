import assert from "node:assert/strict";
import test from "node:test";
import {
  MAX_ANNOTATIONS, addAnnotation, annotationDelivered, annotationReferenceLabel, createAnnotation, editAnnotation,
  markAnnotationSent, readAnnotations, removeAnnotation
} from "./stepAnnotations.js";

test("a chip names a face, edge or vertex by its number, a part by its name, and counts a group", () => {
  assert.equal(annotationReferenceLabel("o1.1.e3"), "Edge 3");
  assert.equal(annotationReferenceLabel("o1.2.f12"), "Face 12");
  assert.equal(annotationReferenceLabel("o1.v4"), "Vertex 4");
  assert.equal(annotationReferenceLabel("o1.2", "Arm"), "Arm");
  assert.equal(annotationReferenceLabel("o1.1.f2,o1.1.f5"), "2 faces");
  assert.equal(annotationReferenceLabel("o1.1.f2,o1.1.e5"), "2 references");
  assert.equal(annotationReferenceLabel("o1.2"), "o1.2");
});

test("an annotation needs something to be pinned to", () => {
  assert.equal(createAnnotation([], "make a hole"), null);
  assert.deepEqual(createAnnotation([{ selector: "o1.1.e3" }], "make a hole in it", { id: "a1" }),
    { id: "a1", references: [{ selector: "o1.1.e3", label: "Edge 3" }], text: "make a hole in it", sent: false });
});

test("editing a sent note makes it unsent; an unchanged edit leaves it alone", () => {
  let list = addAnnotation([], createAnnotation([{ selector: "o1.1.e3" }], "hole", { id: "a1" }));
  list = markAnnotationSent(list, "a1");
  assert.equal(list[0].sent, true);
  assert.equal(editAnnotation(list, "a1", "hole")[0].sent, true);
  const edited = editAnnotation(list, "a1", "bigger hole");
  assert.deepEqual([edited[0].text, edited[0].sent], ["bigger hole", false]);
  assert.deepEqual(removeAnnotation(edited, "a1"), []);
});

test("a stored list is read forgivingly and capped, keeping the newest", () => {
  assert.deepEqual(readAnnotations(null), []);
  assert.deepEqual(readAnnotations([{ id: "x" }, { references: [{ selector: "o1" }] }, "junk"]), []);
  const stored = Array.from({ length: MAX_ANNOTATIONS + 5 }, (_, index) => ({ id: `a${index}`, references: [{ selector: "o1.1.f1" }], text: `${index}` }));
  const read = readAnnotations([...stored, stored[0]]);
  assert.equal(read.length, MAX_ANNOTATIONS);
  assert.equal(read.at(-1).id, `a${MAX_ANNOTATIONS + 4}`);
});

test("only a delivery that reached the chat box counts as sent", () => {
  assert.equal(annotationDelivered({ status: "added", partIds: [] }), true);
  assert.equal(annotationDelivered({ status: "copied", partIds: [] }), true);
  assert.equal(annotationDelivered({ status: "failed" }), false);
  assert.equal(annotationDelivered({ status: "cancelled" }), false);
  assert.equal(annotationDelivered(undefined), false);
});
