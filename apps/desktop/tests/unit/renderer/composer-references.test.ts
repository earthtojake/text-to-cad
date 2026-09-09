import { Editor } from "@tiptap/core";
import Document from "@tiptap/extension-document";
import HardBreak from "@tiptap/extension-hard-break";
import Paragraph from "@tiptap/extension-paragraph";
import Text from "@tiptap/extension-text";
import { afterEach, describe, expect, it } from "vitest";

import { ReferenceNode } from "@renderer/features/session/composer/ReferenceNode";
import { docFromText, parseReference, parseSegments, textFromDoc } from "@renderer/features/session/composer/references";
import { NEW_SESSION_KEY, useComposer } from "@renderer/state/composer";

/**
 * The composer's references (item 4c): the grammar that says which words are
 * chips, the document the editor edits, and the text that comes back out of
 * it — the same characters that went in, chips included.
 */

describe("parseReference", () => {
  it("reads the three forms and nothing else", () => {
    expect(parseReference("models/bracket.step#o1.2")).toEqual({ file: "models/bracket.step", selector: "o1.2" });
    expect(parseReference("bracket.step#label.f45")).toEqual({ file: "bracket.step", selector: "label.f45" });
    expect(parseReference("#o1,o2")).toEqual({ file: "", selector: "o1,o2" });
    expect(parseReference("bracket.step")).toEqual({ file: "bracket.step", selector: "" });
    expect(parseReference("src/bracket.step.py#o1")).toEqual({ file: "src/bracket.step.py", selector: "o1" });
    expect(parseReference("assembly.glb")).toEqual({ file: "assembly.glb", selector: "" });
    // Words with a hash in them, non-CAD files, URLs, prose.
    for (const word of ["C#", "issue#12", "README.md", "README.md#o1", "https://x.y/a.step", "#", "bracket.step#9x", "thicker"]) {
      expect(parseReference(word), word).toBeNull();
    }
  });
});

describe("parseSegments", () => {
  it("keeps the words and the spaces exactly, chips where the references are", () => {
    expect(parseSegments("make bracket.step#o1.2 thicker, then #f3.")).toEqual([
      { type: "text", text: "make " },
      { type: "reference", reference: { file: "bracket.step", selector: "o1.2" } },
      { type: "text", text: " thicker, then " },
      { type: "reference", reference: { file: "", selector: "f3" } },
      { type: "text", text: "." },
    ]);
    expect(parseSegments("no references here")).toEqual([{ type: "text", text: "no references here" }]);
    expect(parseSegments("")).toEqual([]);
  });
});

describe("the document", () => {
  it("round-trips text with chips and newlines", () => {
    for (const text of [
      "make bracket.step#o1.2 thicker",
      "#o1 and #label.f45, please",
      "first line\nsecond line with a.step",
      "  leading and trailing  ",
      "",
      "models/x.step#o1.2",
    ]) {
      expect(textFromDoc(docFromText(text)), JSON.stringify(text)).toBe(text);
    }
  });

  it("puts a chip where the reference is", () => {
    const doc = docFromText("look at bracket.step#o1.2 now");
    expect(doc.content?.[0]?.content).toEqual([
      { type: "text", text: "look at " },
      { type: "reference", attrs: { file: "bracket.step", selector: "o1.2" } },
      { type: "text", text: " now" },
    ]);
  });
});

describe("the editor", () => {
  let editor: Editor | null = null;
  const make = (text: string) => {
    editor = new Editor({
      extensions: [Document.extend({ content: "paragraph" }), Paragraph, Text, HardBreak, ReferenceNode],
      content: docFromText(text),
    });
    return editor;
  };
  afterEach(() => {
    editor?.destroy();
    editor = null;
  });

  it("turns a typed reference into a chip when the space after it lands, punctuation kept", async () => {
    const instance = make("make ");
    instance.commands.focus("end");
    instance.commands.insertContent("bracket.step#o1.2, ", { applyInputRules: true });
    // The rule runs on a timer after a simulated input.
    await new Promise((resolve) => setTimeout(resolve, 20));
    const json = instance.getJSON();
    const content = (json.content?.[0]?.content ?? []) as Array<{ type: string; attrs?: unknown; text?: string }>;
    expect(content.map((node) => node.type)).toEqual(["text", "reference", "text"]);
    expect(content[1]?.attrs).toEqual({ file: "bracket.step", selector: "o1.2" });
    expect(content[2]?.text).toBe(", ");
    expect(textFromDoc(json as never)).toBe("make bracket.step#o1.2, ");

    // A word that is not a reference is left alone.
    instance.commands.insertContent("thicker ", { applyInputRules: true });
    await new Promise((resolve) => setTimeout(resolve, 20));
    expect(textFromDoc(instance.getJSON() as never)).toBe("make bracket.step#o1.2, thicker ");
  });

  it("removes a chip whole on Backspace and leaves the words around it", () => {
    const instance = make("make bracket.step#o1.2 thicker");
    // The caret right after the chip: "make " + one atom.
    instance.commands.setTextSelection(1 + "make ".length + 1);
    expect(instance.commands.keyboardShortcut("Backspace")).toBe(true);
    expect(textFromDoc(instance.getJSON() as never)).toBe("make  thicker");
    expect(instance.getText()).toBe("make  thicker");
    // And Delete before one, the same; a caret beside words is left to the
    // editor's own Backspace (the browser's, which a headless editor has not).
    const again = make("see #f3 here");
    again.commands.setTextSelection(1 + "see ".length);
    expect(again.commands.keyboardShortcut("Delete")).toBe(true);
    expect(textFromDoc(again.getJSON() as never)).toBe("see  here");
    again.commands.setTextSelection(2);
    again.commands.keyboardShortcut("Backspace");
    expect(textFromDoc(again.getJSON() as never)).toBe("see  here");
  });

  it("selects a chip as one unit from the keyboard", () => {
    const instance = make("see bracket.step#o1 here");
    instance.commands.setNodeSelection(1 + "see ".length);
    expect(instance.state.selection.constructor.name).toBe("NodeSelection");
    instance.commands.deleteSelection();
    expect(textFromDoc(instance.getJSON() as never)).toBe("see  here");
  });
});

describe("the composer store", () => {
  it("keeps part names separate from prompt tokens and scoped to their draft", () => {
    useComposer.setState({ drafts: {}, referenceLabels: {} });
    const reference = { file: "models/car.step", selector: "o1.3", label: "wheel_front_left" };
    useComposer.getState().insertReference("car", reference);
    useComposer.getState().insertReference("other", { ...reference, label: "different_part" });
    expect(useComposer.getState().drafts.car).toBe("models/car.step#o1.3 ");
    expect(useComposer.getState().referenceLabels.car?.["models/car.step#o1.3"]).toBe("wheel_front_left");
    expect(useComposer.getState().referenceLabels.other?.["models/car.step#o1.3"]).toBe("different_part");
    useComposer.getState().setDraft("car", "");
    expect(useComposer.getState().referenceLabels.car).toBeUndefined();
    expect(useComposer.getState().referenceLabels.other).toBeDefined();
  });
  it("appends a reference to the draft as its token, spaced", () => {
    useComposer.setState({ drafts: {}, pendingFiles: {} });
    useComposer.getState().insertReference(NEW_SESSION_KEY, { file: "models/x.step", selector: "o1.2" });
    expect(useComposer.getState().drafts[NEW_SESSION_KEY]).toBe("models/x.step#o1.2 ");
    useComposer.getState().setDraft("s1", "make it");
    useComposer.getState().insertReference("s1", { file: "", selector: "f3" });
    expect(useComposer.getState().drafts.s1).toBe("make it #f3 ");
  });

  it("queues a file until the composer takes it", () => {
    useComposer.setState({ drafts: {}, pendingFiles: {} });
    const file = new File(["png"], "view.png", { type: "image/png" });
    useComposer.getState().attachFile("s1", file);
    expect(useComposer.getState().pendingFiles.s1).toEqual([file]);
    expect(useComposer.getState().takeFiles("s1")).toEqual([file]);
    expect(useComposer.getState().pendingFiles.s1).toBeUndefined();
    expect(useComposer.getState().takeFiles("s1")).toEqual([]);
  });
});
