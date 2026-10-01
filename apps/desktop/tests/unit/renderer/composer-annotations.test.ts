import type { PromptReference } from "@text-to-cad/core/prompt";
import { beforeEach, expect, it, vi } from "vitest";

import { createDesktopPromptContext } from "@renderer/features/explorer/host/promptContext";
import { openAnnotation, withAnnotations } from "@renderer/features/session/composer/AnnotationsChip";
import { useComposer } from "@renderer/state/composer";
import type { DraftPart } from "@renderer/state/composer";
import { useExplorer } from "@renderer/state/explorer";
import { useSessions } from "@renderer/state/sessions";
import type { FileTab } from "@shared/types";

const key = "session-1";
const edge = (selector: string, label?: string): PromptReference => ({
  resource: { kind: "workspace-file", workspaceId: "w", path: "parts/bracket.step" },
  target: { kind: "cad-selector", selectors: [selector] },
  ...(label ? { label } : {}),
});
const annotation = (id: string, text: string): DraftPart => ({ id, kind: "annotation", text, references: [edge("o1.1.e3", "Edge 3")] });

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

it("an annotation deleted on the model leaves the draft, and the rest stay; removing nothing changes nothing", () => {
  useComposer.getState().acceptContext(key, "op-1", [annotation("a1", "hole"), annotation("a2", "fillet")], { root: "/p", focus: false });
  useComposer.getState().removeAnnotations(key, ["a1"]);
  expect(useComposer.getState().annotations[key]?.map(item => item.id)).toEqual(["a2"]);
  const before = useComposer.getState();
  useComposer.getState().removeAnnotations(key, ["missing"]);
  useComposer.getState().removeAnnotations("no-such-draft");
  expect(useComposer.getState()).toBe(before);
});

it("sending writes the annotations after the prompt as a numbered list of geometry and notes", () => {
  const annotations = [
    { id: "a1", text: "make a hole in it", references: [edge("o1.1.e3", "Edge 3")] },
    { id: "a2", text: "fillet it", references: [edge("o1.2")] },
  ];
  expect(withAnnotations("Make these changes.", annotations)).toBe(
    "Make these changes.\n\nAnnotations:\n1. parts/bracket.step#o1.1.e3 (Edge 3): make a hole in it\n2. parts/bracket.step#o1.2: fillet it",
  );
  expect(withAnnotations("", annotations)).toMatch(/^Annotations:\n1\. /);
  expect(withAnnotations("Just text", [])).toBe("Just text");
});

it("pressing an annotation in the chat box opens its model and asks the viewer to open it", () => {
  const openFile = vi.fn(() => ({ id: "bracket-tab" }) as FileTab);
  const openCadAnnotation = vi.fn();
  useExplorer.setState({ projectId: "p", ready: true, tabs: [], activeId: null, openFile, openCadAnnotation });
  openAnnotation({ projectId: "p", root: null }, { id: "a1", text: "fillet these", references: [edge("o1.1.f2", "Face 2")] });
  expect(openFile).toHaveBeenCalledWith("parts/bracket.step", null);
  expect(openCadAnnotation).toHaveBeenCalledWith("bracket-tab", "a1");
  expect(() => openAnnotation(null, { id: "a2", text: "", references: [edge("o1.1.f2")] })).toThrow(/project/);
});

it("the chat box tells the viewer which annotations it holds, and a new answer only when that changes", () => {
  useSessions.setState({ sessions: [{ id: key, projectId: "p", archived: false }] as never });
  const port = createDesktopPromptContext("p", null, "w", key);
  expect(port.getSnapshot().held).toEqual([]);
  useComposer.getState().acceptContext(key, "op-1", [annotation("a1", "hole"), annotation("a2", "fillet")], { root: "/p", focus: false });
  const holding = port.getSnapshot();
  expect(holding.held).toEqual(["a1", "a2"]);
  expect(port.getSnapshot()).toBe(holding);
  useComposer.getState().acceptContext(key, "op-2", [{ id: "t", kind: "text", text: "unrelated" }], { root: "/p", focus: false });
  expect(port.getSnapshot(), "a delivery with no annotation leaves the held list as it was").toBe(holding);
  useComposer.getState().removeAnnotations(key);
  expect(port.getSnapshot().held).toEqual([]);
});

it("a note rewritten in the chat box's list changes only that annotation; an empty or unchanged note is not an edit", () => {
  useComposer.getState().acceptContext(key, "op-1", [annotation("a1", "hole"), annotation("a2", "fillet")], { root: "/p", focus: false });
  useComposer.getState().editAnnotation(key, "a1", "  a 6 mm hole  ");
  expect(useComposer.getState().annotations[key]?.map(item => [item.id, item.text])).toEqual([["a1", "a 6 mm hole"], ["a2", "fillet"]]);
  const before = useComposer.getState();
  useComposer.getState().editAnnotation(key, "a1", "   ");
  useComposer.getState().editAnnotation(key, "a1", "a 6 mm hole");
  useComposer.getState().editAnnotation(key, "missing", "x");
  useComposer.getState().editAnnotation("no-such-draft", "a1", "x");
  expect(useComposer.getState()).toBe(before);
});

it("the chat box tells the viewer what each held annotation now says, so an edit here reaches the model", () => {
  useSessions.setState({ sessions: [{ id: key, projectId: "p", archived: false }] as never });
  const port = createDesktopPromptContext("p", null, "w", key);
  useComposer.getState().acceptContext(key, "op-1", [annotation("a1", "hole")], { root: "/p", focus: false });
  expect(port.getSnapshot().heldText).toEqual({ a1: "hole" });
  useComposer.getState().editAnnotation(key, "a1", "a 6 mm hole");
  expect(port.getSnapshot().heldText).toEqual({ a1: "a 6 mm hole" });
  expect(port.getSnapshot().held).toEqual(["a1"]);
});

it("a note on a sketch keeps the sketch with it, out of the attachment strip, and names it when sent", () => {
  const png = new File([new Uint8Array([137, 80, 78, 71])], "bracket-drawing.png", { type: "image/png" });
  const loose = new File(["hello"], "notes.txt", { type: "text/plain" });
  useComposer.getState().acceptContext(key, "op-1", [
    { id: "sketch", kind: "attachment", file: png },
    { id: "a1", kind: "annotation", text: "round this corner", attachments: ["sketch"],
      references: [{ resource: { kind: "workspace-file", workspaceId: "w", path: "parts/bracket.step" }, target: { kind: "whole-resource" }, label: "Drawing" }] },
    { id: "other", kind: "attachment", file: loose },
  ], { root: "/p", focus: false });
  const state = useComposer.getState();
  expect(state.annotations[key]?.map(item => [item.id, item.text, item.image?.name])).toEqual([["a1", "round this corner", "bracket-drawing.png"]]);
  expect(state.pendingFiles[key]?.map(file => file.name), "the sketch is the note's, the text file the strip's").toEqual(["notes.txt"]);
  expect(withAnnotations("Fix it.", state.annotations[key]!)).toBe(
    "Fix it.\n\nAnnotations:\n1. parts/bracket.step (Drawing): round this corner [sketch: bracket-drawing.png]",
  );
});
