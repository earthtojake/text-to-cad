/**
 * Markdown in and markdown out, with the bytes the person did not touch left
 * exactly as they were.
 *
 * ## Why this is not just a serializer
 *
 * Every WYSIWYG markdown editor parses to a document model and prints the
 * model back. That round trip is *lossy in formatting even when it is lossless
 * in meaning*: remark alone, given this repository's own `AGENTS.md`, returns
 * 149 changed lines out of 210 — a list re-wrapped here, a table's padding
 * recomputed there, `*emphasis*` printed as `_emphasis_`, `&` escaped inside a
 * URL. Save a file after fixing one typo and the diff is the whole document.
 * For files that are read in pull requests, that is not a cosmetic problem.
 *
 * So the unit of fidelity here is the **top-level block**. Each one is loaded
 * with the exact slice of the file it came from (`mdSource`) and the exact
 * whitespace that preceded it (`mdGap`). On the way out, a block that still
 * matches the document as it was loaded is written back verbatim, and only the
 * blocks that changed are printed by remark. Editing one paragraph rewrites
 * that paragraph's lines and nothing else.
 *
 * "Still matches" is decided by comparing the block against the one built from
 * that same source at load time — not by re-parsing, and not by watching
 * transactions. A comparison cannot drift the way a dirty flag can.
 *
 * ## Why remark
 *
 * It is the parser the preview already used (Streamdown's), so the editor and
 * the preview agree about what the file says by construction, and it is the
 * highest-fidelity markdown printer in JavaScript. It was also already in the
 * tree. The alternative on offer — `tiptap-markdown`, over markdown-it and
 * prosemirror-markdown — parses to a lossier model and prints a coarser file.
 */
import type { JSONContent } from "@tiptap/core";
import type {
  BlockContent,
  DefinitionContent,
  Heading,
  List,
  ListItem,
  PhrasingContent,
  Root,
  RootContent,
  Table,
  TableCell,
  TableRow,
} from "mdast";
import remarkGfm from "remark-gfm";
import remarkParse from "remark-parse";
import remarkStringify, { type Options as StringifyOptions } from "remark-stringify";
import { unified } from "unified";

/* -------------------------------------------------------------------------- */
/* The frame a document is read and written through                            */
/* -------------------------------------------------------------------------- */

export type MarkdownFrame = {
  /** Everything after the last block: the file's trailing newlines. */
  trailing: string;
  /** How this file writes markdown, sniffed from the file itself. */
  options: StringifyOptions;
  /**
   * Every block — and every list item — as it was loaded, keyed by the source
   * it was built from. One that still equals its entry is written back byte
   * for byte.
   */
  pristine: Map<string, string>;
  /**
   * The column this file wraps prose at, or null when it does not wrap.
   *
   * remark prints a paragraph as one line however long it is. In a file whose
   * every paragraph is wrapped at seventy-eight columns, an edited paragraph
   * would come back as one four-hundred-character line — a diff nobody asked
   * for, in the one block that was legitimately going to change.
   */
  wrap: number | null;
};

export type MarkdownDocument = { doc: JSONContent; frame: MarkdownFrame };

const parser = unified().use(remarkParse).use(remarkGfm);

/**
 * The conventions this file already follows.
 *
 * A document that writes `*` bullets and `*emphasis*` should keep writing them
 * in the one list the person edited, or the edit reformats lines it did not
 * touch. Counting is enough: markdown files are consistent about this, and a
 * file that is not has no convention to preserve.
 */
function sniff(source: string): StringifyOptions {
  const count = (pattern: RegExp) => (source.match(pattern) ?? []).length;
  return {
    bullet: count(/^\s*\*\s/gm) > count(/^\s*-\s/gm) ? "*" : "-",
    // `_emphasis_` against `*emphasis*`, counted without the `**strong**` that
    // shares the character.
    emphasis: count(/(?<!_)_(?!_)/g) > count(/(?<!\*)\*(?!\*)/g) ? "_" : "*",
    strong: "*",
    fence: "`",
    fences: true,
    listItemIndent: "one",
    rule: count(/^\*{3,}\s*$/gm) > count(/^-{3,}\s*$/gm) ? "*" : "-",
    ruleSpaces: false,
    resourceLink: false,
    tightDefinitions: true,
  };
}

/**
 * Does this file wrap its prose, and at what column?
 *
 * Only paragraphs are measured, and only their non-final lines: the last line
 * of a paragraph is however long the sentence ended up. A file with no
 * paragraph longer than one line has no wrap to preserve, and one whose
 * paragraphs run past a hundred columns is not wrapped on purpose.
 */
function sniffWrap(root: Root, source: string): number | null {
  const widths: number[] = [];
  for (const node of root.children) {
    if (node.type !== "paragraph") {
      continue;
    }
    const lines = sliceOf(node, source).split("\n");
    widths.push(...lines.slice(0, -1).map((line) => line.length));
  }
  if (widths.length === 0) {
    return null;
  }
  const longest = Math.max(...widths);
  return longest > 100 ? null : longest;
}

/**
 * Re-wrap printed prose at `width`, hanging the continuation lines under
 * whatever marker the line starts with.
 *
 * Line by line, because the newlines remark did print are hard breaks and
 * moving one would change what the document says. A line that is a table row,
 * a fence or indented code is left exactly as it is: those are not prose, and
 * a break in the wrong place there changes the block's type.
 */
function rewrap(text: string, width: number): string {
  return text
    .split("\n")
    .map((line) => {
      if (line.length <= width || /^(\s{4,}|\s*(?:\||```|~~~))/.test(line)) {
        return line;
      }
      const marker = /^\s*(?:[-*+]\s+|\d+[.)]\s+|>\s+)?/.exec(line)?.[0] ?? "";
      const indent = " ".repeat(marker.length);
      const words = line.slice(marker.length).split(" ");
      const lines: string[] = [];
      let current = marker;
      for (const word of words) {
        const candidate = current === marker || current === indent ? current + word : `${current} ${word}`;
        if (candidate.length > width && current !== marker && current !== indent) {
          lines.push(current);
          current = indent + word;
        } else {
          current = candidate;
        }
      }
      lines.push(current);
      // A wrapped line that now begins with something markdown reads as a new
      // block would change the document; leave the whole line long instead.
      return lines.slice(1).some((wrapped) => /^\s*(?:[-*+>#]|\d+[.)])\s/.test(wrapped))
        ? line
        : lines.join("\n");
    })
    .join("\n");
}

/* -------------------------------------------------------------------------- */
/* Reading                                                                     */
/* -------------------------------------------------------------------------- */

/** Parse a file into an editor document and the frame that writes it back. */
export function markdownToDocument(source: string): MarkdownDocument {
  const root = parser.parse(source) as Root;
  const options = sniff(source);
  const pristine = new Map<string, string>();

  const content: JSONContent[] = [];
  let cursor = 0;
  for (const child of root.children) {
    const start = child.position?.start.offset ?? cursor;
    const end = child.position?.end.offset ?? cursor;
    const block = blockToJson(child, source);
    if (!block) {
      continue;
    }
    const slice = source.slice(start, end);
    block.attrs = { ...block.attrs, mdSource: slice, mdGap: source.slice(cursor, start) };
    record(pristine, block);
    content.push(block);
    cursor = end;
  }

  return {
    doc: { type: "doc", content: content.length > 0 ? content : [{ type: "paragraph" }] },
    frame: { trailing: source.slice(cursor), options, pristine, wrap: sniffWrap(root, source) },
  };
}

/**
 * Re-take the pristine fingerprints from a document the editor has loaded.
 *
 * ProseMirror normalises what it is given — it fills in every attribute the
 * schema declares, in the schema's order, and drops what the schema has no
 * room for. Fingerprints taken from the JSON *this module* built would then
 * disagree with the ones taken from `editor.getJSON()` on a document nobody
 * touched, and every block would be re-printed on the first save. So the
 * editor's own reading of the untouched document is the one that is recorded.
 */
export function capturePristine(frame: MarkdownFrame, doc: JSONContent): void {
  frame.pristine.clear();
  for (const block of doc.content ?? []) {
    record(frame.pristine, block);
  }
}

/** A block and, when it is a list, each of its items. */
function record(pristine: Map<string, string>, block: JSONContent): void {
  const source = block.attrs?.mdSource;
  if (typeof source === "string") {
    pristine.set(source, fingerprint(block));
  }
  if (LIST_TYPES.has(block.type ?? "")) {
    for (const item of block.content ?? []) {
      const itemSource = item.attrs?.mdSource;
      if (typeof itemSource === "string") {
        pristine.set(itemSource, fingerprint(item));
      }
    }
  }
}

const LIST_TYPES = new Set(["bulletList", "orderedList", "taskList"]);

/* -------------------------------------------------------------------------- */
/* Writing                                                                     */
/* -------------------------------------------------------------------------- */

/** Print an editor document back to markdown. */
export function documentToMarkdown(doc: JSONContent, frame: MarkdownFrame): string {
  const printer = unified().use(remarkStringify, frame.options).use(remarkGfm) as unknown as Printer;
  const out: string[] = [];

  (doc.content ?? []).forEach((block, index) => {
    const gap = index === 0 ? "" : ((block.attrs?.mdGap as string | undefined) ?? "\n\n");
    out.push(gap, blockToMarkdown(block, frame, printer));
  });

  return out.join("") + frame.trailing;
}

type Printer = { stringify: (tree: Root) => string };

function blockToMarkdown(block: JSONContent, frame: MarkdownFrame, printer: Printer): string {
  if (unchanged(block, frame)) {
    return block.attrs!.mdSource as string;
  }
  if (LIST_TYPES.has(block.type ?? "")) {
    return listToMarkdown(block, frame, printer);
  }
  return print(jsonToBlock(block), frame, printer);
}

/** A list, item by item, so an untouched bullet keeps its own lines. */
function listToMarkdown(block: JSONContent, frame: MarkdownFrame, printer: Printer): string {
  const first = (block.attrs?.start as number | undefined) ?? 1;
  const out: string[] = [];

  (block.content ?? []).forEach((item, index) => {
    out.push(index === 0 ? "" : ((item.attrs?.mdGap as string | undefined) ?? "\n"));
    if (unchanged(item, frame)) {
      out.push(item.attrs!.mdSource as string);
      return;
    }
    // One item, printed as the one-item list it would be — which is how it
    // picks up this file's bullet character and this item's own number.
    const single = jsonToList({ ...block, attrs: { ...block.attrs, start: first + index }, content: [item] });
    out.push(print(single, frame, printer));
  });

  return out.join("");
}

function unchanged(node: JSONContent, frame: MarkdownFrame): boolean {
  const source = node.attrs?.mdSource;
  return typeof source === "string" && frame.pristine.get(source) === fingerprint(node);
}

function print(node: RootContent | null, frame: MarkdownFrame, printer: Printer): string {
  if (!node) {
    return "";
  }
  // `stringify` always ends a document with a newline; the gaps between blocks
  // are this module's job, not remark's.
  const text = printer.stringify({ type: "root", children: [node] } as Root).replace(/\n+$/, "");
  return frame.wrap === null ? text : rewrap(text, frame.wrap);
}

/**
 * A block's identity for "has this changed": its content and the attributes
 * that reach the file, with the two bookkeeping attributes left out.
 */
function fingerprint(block: JSONContent): string {
  return JSON.stringify(block, (key, value) =>
    key === "mdSource" || key === "mdGap" ? undefined : (value as unknown),
  );
}

/* -------------------------------------------------------------------------- */
/* mdast -> editor                                                             */
/* -------------------------------------------------------------------------- */

/**
 * One block. Anything the schema has no node for — a raw HTML block, a link
 * reference definition, a footnote — becomes a `markdownRaw` atom holding its
 * own source: it renders as what it is and writes back unchanged, which is the
 * honest answer for a construct this editor cannot edit.
 */
function blockToJson(node: RootContent, source: string): JSONContent | null {
  switch (node.type) {
    case "paragraph":
      return { type: "paragraph", content: inlineToJson(node.children, source) };
    case "heading":
      return {
        type: "heading",
        attrs: { level: (node as Heading).depth },
        content: inlineToJson(node.children, source),
      };
    case "thematicBreak":
      return { type: "horizontalRule" };
    case "blockquote":
      return {
        type: "blockquote",
        content: node.children.map((child) => blockToJson(child, source)).filter(isJson),
      };
    case "code":
      return {
        type: "codeBlock",
        attrs: { language: node.lang ?? null },
        content: node.value === "" ? undefined : [{ type: "text", text: node.value }],
      };
    case "list":
      return listToJson(node as List, source);
    case "table":
      return tableToJson(node as Table, source);
    default:
      return { type: "markdownRaw", attrs: { text: sliceOf(node, source) } };
  }
}

/**
 * A list, with every *item* carrying its own slice as well.
 *
 * The block is the unit of fidelity everywhere else, but a list is one block
 * and a document's lists are long: editing one bullet of nine would re-print
 * the eight the person never touched, and in a hard-wrapped file that is eight
 * paragraphs joined into eight long lines. An item is small enough to be the
 * unit here and large enough to be worth it.
 */
function listToJson(list: List, source: string): JSONContent {
  // A GFM task list is a list whose items carry a checkbox. Mixed lists are
  // not a thing markdown can express, so one checked item settles it.
  const task = list.children.some((item) => typeof (item as ListItem).checked === "boolean");
  let cursor = list.position?.start.offset ?? 0;
  const items = list.children.map((item) => {
    const content = item.children.map((child) => blockToJson(child, source)).filter(isJson);
    const start = item.position?.start.offset ?? cursor;
    const end = item.position?.end.offset ?? cursor;
    const attrs = {
      mdSource: source.slice(start, end),
      mdGap: source.slice(cursor, start),
      ...(task ? { checked: item.checked === true } : {}),
    };
    cursor = end;
    return { type: task ? "taskItem" : "listItem", attrs, content };
  });
  if (task) {
    return { type: "taskList", content: items };
  }
  return list.ordered
    ? { type: "orderedList", attrs: { start: list.start ?? 1 }, content: items }
    : { type: "bulletList", content: items };
}

function tableToJson(table: Table, source: string): JSONContent {
  const align = (table.align ?? []).map((value) => value ?? null);
  const rows = table.children.map((row, index) => ({
    type: "tableRow",
    content: (row as TableRow).children.map((cell) => ({
      type: index === 0 ? "tableHeader" : "tableCell",
      content: [{ type: "paragraph", content: inlineToJson((cell as TableCell).children, source) }],
    })),
  }));
  // The column alignments have no home in the editor's table, and losing them
  // turns `|---:|` into `|---|` the first time a cell is edited.
  return { type: "table", attrs: { mdAlign: align }, content: rows };
}

const MARK_OF: Record<string, string> = {
  emphasis: "italic",
  strong: "bold",
  delete: "strike",
};

function inlineToJson(nodes: PhrasingContent[], source: string): JSONContent[] {
  const out: JSONContent[] = [];

  const walk = (children: PhrasingContent[], marks: MarkJson[]) => {
    for (const node of children) {
      switch (node.type) {
        case "text":
          out.push(withMarks({ type: "text", text: soft(node.value) }, marks));
          break;
        case "inlineCode":
          out.push(withMarks({ type: "text", text: node.value }, [...marks, { type: "code" }]));
          break;
        case "emphasis":
        case "strong":
        case "delete":
          walk(node.children, [...marks, { type: MARK_OF[node.type]! }]);
          break;
        case "link":
          walk(node.children, [
            ...marks,
            { type: "link", attrs: { href: node.url, title: node.title ?? null } },
          ]);
          break;
        case "image":
          out.push({
            type: "image",
            attrs: { src: node.url, alt: node.alt ?? null, title: node.title ?? null },
          });
          break;
        case "break":
          out.push({ type: "hardBreak" });
          break;
        default:
          // Inline HTML, footnote and reference syntax: kept as the literal
          // characters they are, so the paragraph reads the way the file does.
          out.push(withMarks({ type: "text", text: soft(sliceOf(node, source)) }, marks));
      }
    }
  };

  walk(nodes, []);
  return out.filter((node) => node.type !== "text" || node.text !== "");
}

type MarkJson = { type: string; attrs?: Record<string, unknown> };

/**
 * A soft line break is a space.
 *
 * That is what markdown means by it, and ProseMirror draws its content with
 * `white-space: pre-wrap` — so a hard-wrapped paragraph carried in with its
 * newlines intact renders as a paragraph broken at every seventy-eighth
 * column. A *hard* break is an mdast `break` node and survives on its own.
 */
function soft(text: string): string {
  return text.replace(/[ \t]*\r?\n[ \t]*/g, " ");
}

function withMarks(node: JSONContent, marks: MarkJson[]): JSONContent {
  return marks.length > 0 ? { ...node, marks } : node;
}

function sliceOf(node: RootContent | PhrasingContent, source: string): string {
  const start = node.position?.start.offset;
  const end = node.position?.end.offset;
  return start === undefined || end === undefined
    ? ("value" in node && typeof node.value === "string" ? node.value : "")
    : source.slice(start, end);
}

/* -------------------------------------------------------------------------- */
/* editor -> mdast                                                             */
/* -------------------------------------------------------------------------- */

function jsonToBlock(block: JSONContent): RootContent | null {
  switch (block.type) {
    case "paragraph":
      return { type: "paragraph", children: jsonToInline(block.content ?? []) };
    case "heading":
      return {
        type: "heading",
        depth: clampDepth(block.attrs?.level),
        children: jsonToInline(block.content ?? []),
      };
    case "horizontalRule":
      return { type: "thematicBreak" };
    case "blockquote":
      return {
        type: "blockquote",
        children: (block.content ?? []).map(jsonToBlock).filter(isBlockContent),
      };
    case "codeBlock":
      return {
        type: "code",
        lang: (block.attrs?.language as string | null) ?? null,
        value: textOf(block),
      };
    case "bulletList":
    case "orderedList":
    case "taskList":
      return jsonToList(block);
    case "table":
      return jsonToTable(block);
    case "markdownRaw":
      return { type: "html", value: (block.attrs?.text as string | undefined) ?? "" };
    default:
      return null;
  }
}

function jsonToList(block: JSONContent): List {
  const ordered = block.type === "orderedList";
  return {
    type: "list",
    ordered,
    start: ordered ? ((block.attrs?.start as number | undefined) ?? 1) : null,
    spread: false,
    children: (block.content ?? []).map((item) => ({
      type: "listItem",
      spread: false,
      checked: item.type === "taskItem" ? item.attrs?.checked === true : null,
      children: (item.content ?? []).map(jsonToBlock).filter(isBlockContent),
    })),
  };
}

function jsonToTable(block: JSONContent): Table {
  const align = (block.attrs?.mdAlign as (Table["align"] extends (infer A)[] ? A : never)[]) ?? [];
  return {
    type: "table",
    align,
    children: (block.content ?? []).map((row) => ({
      type: "tableRow",
      children: (row.content ?? []).map((cell) => ({
        type: "tableCell",
        // A cell holds a paragraph in the editor and phrasing in markdown.
        children: (cell.content ?? []).flatMap((child) => jsonToInline(child.content ?? [])),
      })),
    })),
  };
}

/**
 * Inline content, with the marks turned back into nesting.
 *
 * The order is the one markdown reads best: a link outside the emphasis
 * inside it, and code innermost, because `` `*x*` `` is code containing
 * asterisks while `*`x`*` is emphasis containing code.
 */
const MARK_ORDER = ["link", "strike", "bold", "italic", "code"] as const;

function jsonToInline(nodes: JSONContent[]): PhrasingContent[] {
  const out: PhrasingContent[] = [];
  for (const node of merge(nodes)) {
    if (node.type === "image") {
      out.push({
        type: "image",
        url: (node.attrs?.src as string | undefined) ?? "",
        alt: (node.attrs?.alt as string | null) ?? null,
        title: (node.attrs?.title as string | null) ?? null,
      });
      continue;
    }
    if (node.type === "hardBreak") {
      out.push({ type: "break" });
      continue;
    }
    if (node.type !== "text") {
      continue;
    }

    const marks: MarkJson[] = node.marks ?? [];
    const code = marks.find((mark) => mark.type === "code");
    let built: PhrasingContent = code
      ? { type: "inlineCode", value: node.text ?? "" }
      : { type: "text", value: node.text ?? "" };

    for (const name of [...MARK_ORDER].reverse()) {
      const mark = marks.find((candidate) => candidate.type === name);
      if (!mark || name === "code") {
        continue;
      }
      if (name === "link") {
        built = {
          type: "link",
          url: (mark.attrs?.href as string | undefined) ?? "",
          title: (mark.attrs?.title as string | null) ?? null,
          children: [built],
        };
      } else {
        built = {
          type: name === "bold" ? "strong" : name === "italic" ? "emphasis" : "delete",
          children: [built],
        };
      }
    }
    out.push(built);
  }
  return out;
}

/**
 * Join runs of text that carry the same marks.
 *
 * Without this, a paragraph the editor happens to hold as two adjacent bold
 * spans prints as `**one****two**`, which is four asterisks where the file had
 * two and a diff on a line nobody edited.
 */
function merge(nodes: JSONContent[]): JSONContent[] {
  const out: JSONContent[] = [];
  for (const node of nodes) {
    const previous = out[out.length - 1];
    if (
      previous &&
      previous.type === "text" &&
      node.type === "text" &&
      JSON.stringify(previous.marks ?? []) === JSON.stringify(node.marks ?? [])
    ) {
      out[out.length - 1] = { ...previous, text: (previous.text ?? "") + (node.text ?? "") };
      continue;
    }
    out.push(node);
  }
  return out;
}

/* -------------------------------------------------------------------------- */
/* Small shared pieces                                                         */
/* -------------------------------------------------------------------------- */

function textOf(block: JSONContent): string {
  return (block.content ?? []).map((child) => child.text ?? "").join("");
}

function clampDepth(level: unknown): Heading["depth"] {
  const depth = typeof level === "number" ? Math.min(6, Math.max(1, Math.round(level))) : 1;
  return depth as Heading["depth"];
}

function isJson(value: JSONContent | null): value is JSONContent {
  return value !== null;
}

function isBlockContent(value: RootContent | null): value is BlockContent | DefinitionContent {
  return value !== null;
}
