import { Editor } from "@tiptap/core";
import { afterEach, describe, expect, it } from "vitest";

// See `markdown-document.test.ts`: the repository's own files, as bytes.
import AGENTS from "../../../../../AGENTS.md?raw";
import CONTRIBUTING from "../../../../../CONTRIBUTING.md?raw";
import README from "../../../../../README.md?raw";

import {
  capturePristine,
  documentToMarkdown,
  markdownToDocument,
} from "./document.js";
import { markdownExtensions } from "./schema.js";

/**
 * The same contract as `markdown-document.test.ts`, but through a real
 * ProseMirror document rather than the JSON the bridge builds.
 *
 * This is the test that matters, and it is the one that would have caught the
 * whole feature failing quietly: ProseMirror normalises a document as it loads
 * it — it fills in every attribute the schema declares and drops what the
 * schema has no room for — so a fingerprint taken before the load does not
 * match one taken after, and *every* block would be re-printed on the first
 * save while every unit test over the bridge alone stayed green.
 */

const FILES: [string, string][] = [
  ["README.md", README],
  ["AGENTS.md", AGENTS],
  ["CONTRIBUTING.md", CONTRIBUTING],
];
const LINE_ENDINGS = [["LF", "\n"], ["CRLF", "\r\n"]] as const;
// Test Windows and Unix inputs regardless of this checkout's line endings.
const FILE_CASES = FILES.flatMap(([name, source]) =>
  LINE_ENDINGS.map(([ending, newline]) => [
    `${name} (${ending})`, source.replace(/\r?\n/g, newline),
  ] as const),
);

let editor: Editor | null = null;

afterEach(() => {
  editor?.destroy();
  editor = null;
});

function open(source: string) {
  const { doc, frame } = markdownToDocument(source);
  editor = new Editor({
    element: document.createElement("div"),
    extensions: markdownExtensions,
    content: doc,
  });
  capturePristine(frame, editor.getJSON());
  return { editor, frame };
}

describe("the markdown editor", () => {
  it.each(FILE_CASES)("gives %s back unchanged when nothing is typed", (_name, source) => {
    const { editor: instance, frame } = open(source);
    expect(documentToMarkdown(instance.getJSON(), frame)).toBe(source);
  });

  it.each(LINE_ENDINGS)("rewrites one block's lines and no others (%s)", (_ending, newline) => {
    const source = AGENTS.replace(/\r?\n/g, newline);
    const { editor: instance, frame } = open(source);
    const edited = instance.getJSON().content![0]!.attrs!.mdSource as string;

    // Type into the first block, the way a person does: put the caret at the
    // end of it and insert a word.
    const at = instance.state.doc.resolve(1).after(1) - 1;
    instance.commands.insertContentAt(at, " Really.");

    const out = documentToMarkdown(instance.getJSON(), frame);
    expect(out).toContain("Really.");

    // Every other line of the file is still there, and the count of lines that
    // are not is the one paragraph's.
    const before = new Set(source.split(/\r?\n/));
    const after = new Set(out.split(/\r?\n/));
    const gone = [...before].filter((line) => !after.has(line) && line.trim() !== "");
    // The block the caret was in, and nothing else in a 210-line file.
    expect(gone).toEqual(edited.split(/\r?\n/));
    // Also compare bytes, so ignoring line delimiters cannot hide a rewrite
    // of an untouched block or its surrounding whitespace.
    expect(out).toBe(source.replace(edited, `${edited} Really.`));
  });

  it("writes a heading typed with markdown as a heading", () => {
    const { editor: instance, frame } = open("Body.\n");
    instance.commands.setTextSelection(1);
    instance.commands.insertContent("## Title\n");
    expect(documentToMarkdown(instance.getJSON(), frame)).toContain("## Title");
  });

  it("keeps a raw HTML block through a load and a save", () => {
    const source = '<div align="center">\n\nHi.\n\n</div>\n';
    const { editor: instance, frame } = open(source);
    expect(documentToMarkdown(instance.getJSON(), frame)).toBe(source);
  });

  it("keeps a task list's checkboxes", () => {
    const source = "- [ ] one\n- [x] two\n";
    const { editor: instance, frame } = open(source);
    expect(documentToMarkdown(instance.getJSON(), frame)).toBe(source);
  });
});
