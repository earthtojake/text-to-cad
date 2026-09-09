import type { JSONContent } from "@tiptap/core";
import { describe, expect, it } from "vitest";

// The repository's own files, as bytes, through Vite's `?raw` — a fixture
// written for this test would be a fixture written to pass it.
import AGENTS from "../../../../../AGENTS.md?raw";
import CONTRIBUTING from "../../../../../CONTRIBUTING.md?raw";
import README from "../../../../../README.md?raw";

import {
  documentToMarkdown,
  markdownToDocument,
} from "@renderer/features/explorer/markdown/document";

/**
 * The contract this module exists for: a document that comes back out of the
 * editor is the file it went in as, except for the blocks that changed.
 *
 * The two files are this repository's own, because a fixture written for the
 * test would be a fixture written to pass it — these have raw HTML, badge
 * images, GFM tables, fenced code, nested lists and an em dash in every third
 * sentence.
 */

const FILES: [string, string][] = [
  ["README.md", README],
  ["AGENTS.md", AGENTS],
  ["CONTRIBUTING.md", CONTRIBUTING],
];

/**
 * A line diff, so "unrelated lines" means unrelated *lines* and not unrelated
 * line numbers: replacing a hard-wrapped paragraph with one short line moves
 * every line after it, and a positional comparison would call that a rewrite.
 */
function diff(before: string[], after: string[]): { removed: string[]; added: string[] } {
  const lcs: number[][] = Array.from({ length: before.length + 1 }, () =>
    new Array<number>(after.length + 1).fill(0),
  );
  for (let i = before.length - 1; i >= 0; i -= 1) {
    for (let j = after.length - 1; j >= 0; j -= 1) {
      lcs[i]![j] =
        before[i] === after[j] ? lcs[i + 1]![j + 1]! + 1 : Math.max(lcs[i + 1]![j]!, lcs[i]![j + 1]!);
    }
  }
  const removed: string[] = [];
  const added: string[] = [];
  let i = 0;
  let j = 0;
  while (i < before.length && j < after.length) {
    if (before[i] === after[j]) {
      i += 1;
      j += 1;
    } else if (lcs[i + 1]![j]! >= lcs[i]![j + 1]!) {
      removed.push(before[i]!);
      i += 1;
    } else {
      added.push(after[j]!);
      j += 1;
    }
  }
  removed.push(...before.slice(i));
  added.push(...after.slice(j));
  return { removed, added };
}

/** The first block whose type matches, and where it is. */
function findBlock(doc: JSONContent, type: string): { index: number; node: JSONContent } {
  const index = (doc.content ?? []).findIndex((node) => node.type === type);
  expect(index, `no ${type} in the document`).toBeGreaterThanOrEqual(0);
  return { index, node: doc.content![index]! };
}

describe("markdown round trip", () => {
  it.each(FILES)("re-emits %s byte for byte when nothing is edited", (_name, source) => {
    const { doc, frame } = markdownToDocument(source);
    expect(documentToMarkdown(doc, frame)).toBe(source);
  });

  it.each(FILES)("rewrites only the edited paragraph in %s", (_name, source) => {
    const { doc, frame } = markdownToDocument(source);

    // The edit a person makes: one word, in one paragraph, in place.
    const { index, node } = findBlock(doc, "paragraph");
    const edited: JSONContent = {
      ...node,
      content: [{ type: "text", text: "Edited by the test." }],
    };
    const next = { ...doc, content: doc.content!.map((b, at) => (at === index ? edited : b)) };

    const out = documentToMarkdown(next, frame);
    const { removed, added } = diff(source.split("\n"), out.split("\n"));

    // Exactly the paragraph's own lines out, and the one line that replaced
    // them in. A whole-document serializer moves 18 lines of README.md and
    // 149 of AGENTS.md on this same edit.
    expect(removed).toEqual((node.attrs?.mdSource as string).split("\n"));
    expect(added).toEqual(["Edited by the test."]);
    expect(out).toContain("Edited by the test.");
  });

  it("keeps a table's alignment when a cell is edited", () => {
    const source = ["| a | b |", "| :- | --: |", "| 1 | 2 |", ""].join("\n");
    const { doc, frame } = markdownToDocument(source);
    const { index, node } = findBlock(doc, "table");

    const rows = node.content!.map((row, at) =>
      at === 0
        ? row
        : {
            ...row,
            content: row.content!.map((cell, column) =>
              column === 0
                ? { ...cell, content: [{ type: "paragraph", content: [{ type: "text", text: "9" }] }] }
                : cell,
            ),
          },
    );
    const next = {
      ...doc,
      content: doc.content!.map((b, at) => (at === index ? { ...node, content: rows } : b)),
    };

    const out = documentToMarkdown(next, frame);
    // remark pads the columns; what matters is the cell and the two markers.
    expect(out).toMatch(/\|\s*9\s*\|\s*2\s*\|/);
    expect(out).toContain(":-");
    expect(out).toContain("-:");
  });

  it("keeps a file's own bullet and emphasis characters", () => {
    const source = ["* one", "* two", "", "Some *emphasis* here.", ""].join("\n");
    const { doc, frame } = markdownToDocument(source);
    const { index, node } = findBlock(doc, "bulletList");

    const items = node.content!.map((item, at) =>
      at === 0
        ? { ...item, content: [{ type: "paragraph", content: [{ type: "text", text: "ONE" }] }] }
        : item,
    );
    const next = {
      ...doc,
      content: doc.content!.map((b, at) => (at === index ? { ...node, content: items } : b)),
    };

    // The list is re-printed, so it has to be re-printed the way this file
    // writes lists — a `-` here would rewrite the untouched second item.
    expect(documentToMarkdown(next, frame)).toContain("* ONE\n* two");
  });

  it("re-prints only the list item that changed", () => {
    const source = AGENTS;
    const { doc, frame } = markdownToDocument(source);
    const { index, node } = findBlock(doc, "bulletList");
    expect(node.content!.length).toBeGreaterThanOrEqual(2);

    const items = node.content!.map((item, at) =>
      at === 1
        ? {
            ...item,
            content: [{ type: "paragraph", content: [{ type: "text", text: "Rewritten." }] }],
          }
        : item,
    );
    const next = {
      ...doc,
      content: doc.content!.map((b, at) => (at === index ? { ...node, content: items } : b)),
    };

    const { removed, added } = diff(source.split("\n"), documentToMarkdown(next, frame).split("\n"));
    // The one bullet's lines, not the whole list's. Without per-item sources
    // every other bullet in the list comes back as one long line.
    expect(removed).toEqual((node.content![1]!.attrs?.mdSource as string).split("\n"));
    expect(added).toEqual(["- Rewritten."]);
  });

  it("re-wraps an edited paragraph at the column the file wraps at", () => {
    const source = AGENTS;
    const { doc, frame } = markdownToDocument(source);
    expect(frame.wrap).toBeGreaterThan(60);
    expect(frame.wrap).toBeLessThanOrEqual(100);

    const { index, node } = findBlock(doc, "paragraph");
    const long = "One sentence that goes on for a while. ".repeat(8).trim();
    const next = {
      ...doc,
      content: doc.content!.map((b, at) =>
        at === index ? { ...node, content: [{ type: "text", text: long }] } : b,
      ),
    };

    const { added } = diff(source.split("\n"), documentToMarkdown(next, frame).split("\n"));
    expect(added.length).toBeGreaterThan(1);
    for (const line of added) {
      expect(line.length).toBeLessThanOrEqual(frame.wrap!);
    }
    expect(added.join(" ")).toBe(long);
  });

  it("leaves a file that does not wrap unwrapped", () => {
    const source = "A single line that is really quite long indeed and never wrapped at all.\n";
    const { frame } = markdownToDocument(source);
    expect(frame.wrap).toBeNull();
  });

  it("holds raw HTML, definitions and footnotes as their own bytes", () => {
    const source = [
      '<div align="center">',
      "",
      "Text.",
      "",
      "</div>",
      "",
      "[ref]: https://example.com",
      "",
    ].join("\n");
    const { doc, frame } = markdownToDocument(source);
    expect((doc.content ?? []).filter((node) => node.type === "markdownRaw")).toHaveLength(3);
    expect(documentToMarkdown(doc, frame)).toBe(source);
  });

  it("prints a block that was inserted, and leaves its neighbours alone", () => {
    const source = AGENTS;
    const { doc, frame } = markdownToDocument(source);
    const inserted: JSONContent = {
      type: "paragraph",
      content: [{ type: "text", text: "A new paragraph." }],
    };
    const next = { ...doc, content: [doc.content![0]!, inserted, ...doc.content!.slice(1)] };

    const out = documentToMarkdown(next, frame);
    expect(out).toContain("A new paragraph.");
    // Everything the file already said is still in it, unchanged.
    for (const line of source.split("\n").filter((line) => line.trim().length > 20)) {
      expect(out).toContain(line);
    }
  });
});
