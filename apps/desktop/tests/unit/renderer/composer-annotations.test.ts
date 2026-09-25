import { beforeEach, expect, it, vi } from "vitest";

import { openAnnotation, withAnnotations } from "@renderer/features/session/composer/AnnotationsChip";
import { useExplorer } from "@renderer/state/explorer";
import type { FileTab } from "@shared/types";
import { useComposer } from "@renderer/state/composer";
import type { DraftPart } from "@renderer/state/composer";

const key = "session-1";
const annotation = (id: string, text: string): DraftPart => ({
  id, kind: "annotation", text, references: [{ text: "bracket.step#o1.1.e3", label: "Edge 3" }],
});

beforeEach(() => {
  useComposer.setState({ drafts: {}, annotations: {}, acceptedContexts: {}, referenceLabels: {}, pendingFiles: {}, draftRoots: {} });
});

it("annotations from the viewer ride beside the draft's text, not inside it", () => {
  useComposer.getState().setDraft(key, "Make these changes.");
  useComposer.getState().acceptContext(key, "op-1", [annotation("a1", "make a hole in it"), annotation("a2", "fillet it")], { root: "/p", focus: false });
  const state = useComposer.getState();
  expect(state.drafts[key]).toBe("Make these changes.");
  expect(state.annotations[key]?.map(item => [item.id, item.text])).toEqual([["a1", "make a hole in it"], ["a2", "fillet it"]]);
});

it("an annotation added again after an edit replaces its earlier copy", () => {
  useComposer.getState().acceptContext(key, "op-1", [annotation("a1", "make a hole")], { root: "/p", focus: false });
  useComposer.getState().acceptContext(key, "op-2", [annotation("a1", "make a 6 mm hole")], { root: "/p", focus: false });
  expect(useComposer.getState().annotations[key]?.map(item => item.text)).toEqual(["make a 6 mm hole"]);
  useComposer.getState().removeAnnotations(key);
  expect(useComposer.getState().annotations[key]).toBeUndefined();
});

it("sending writes the annotations after the prompt as a numbered list of geometry and notes", () => {
  const annotations = [
    { id: "a1", text: "make a hole in it", references: [{ text: "bracket.step#o1.1.e3", label: "Edge 3" }] },
    { id: "a2", text: "fillet it", references: [{ text: "bracket.step#o1.2" }] },
  ];
  expect(withAnnotations("Make these changes.", annotations)).toBe(
    "Make these changes.\n\nAnnotations:\n1. bracket.step#o1.1.e3 (Edge 3): make a hole in it\n2. bracket.step#o1.2: fillet it",
  );
  expect(withAnnotations("", annotations)).toMatch(/^Annotations:\n1\. /);
  expect(withAnnotations("Just text", [])).toBe("Just text");
});

it("pressing an annotation in the chat box opens its model, selects its geometry and names it", () => {
  const openFile = vi.fn(() => ({ id: "bracket-tab" }) as FileTab);
  const selectCadReference = vi.fn();
  useExplorer.setState({ projectId: "p", ready: true, tabs: [], activeId: null, openFile, selectCadReference });
  openAnnotation({ projectId: "p", root: null }, {
    id: "a1", text: "fillet these",
    references: [{ text: "parts/bracket.step#o1.1.f2", label: "Face 2" }, { text: "parts/bracket.step#o1.1.f5", label: "Face 5" }],
  });
  expect(openFile).toHaveBeenCalledWith("parts/bracket.step", null);
  expect(selectCadReference).toHaveBeenCalledWith("bracket-tab", "o1.1.f2,o1.1.f5", { annotation: "a1" });
  expect(() => openAnnotation(null, { id: "a2", text: "", references: [{ text: "parts/bracket.step#o1.1.f2" }] })).toThrow(/project/);
});

it("an annotation deleted on the model leaves the draft, and the rest stay", () => {
  useComposer.getState().acceptContext(key, "op-1", [annotation("a1", "hole"), annotation("a2", "fillet")], { root: "/p", focus: false });
  useComposer.getState().removeAnnotations(key, ["a1"]);
  expect(useComposer.getState().annotations[key]?.map(item => item.id)).toEqual(["a2"]);
});
