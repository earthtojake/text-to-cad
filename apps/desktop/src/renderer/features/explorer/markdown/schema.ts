/**
 * The editor's schema: TipTap's starter kit, plus the four things markdown has
 * and it does not, plus the two bookkeeping attributes `document.ts` writes.
 *
 * TipTap rather than a hand-built ProseMirror: the starter kit is the schema,
 * the input rules (`## ` becomes a heading as you type it) and the keymap, and
 * none of those are the interesting part of this feature. What TipTap is *not*
 * used for is markdown — `tiptap-markdown` parses with markdown-it and prints
 * with prosemirror-markdown, both a step down from remark, and neither offers
 * a way to keep a block's original bytes. See `document.ts`.
 */
import { Extension, Node } from "@tiptap/core";
import Image from "@tiptap/extension-image";
import { TaskItem, TaskList } from "@tiptap/extension-list";
import { TableKit } from "@tiptap/extension-table";
import StarterKit from "@tiptap/starter-kit";

/**
 * The block types that carry a slice of the file.
 *
 * `markdownRaw` is here too: it *is* a slice of the file and nothing else.
 */
const TOP_LEVEL = [
  "paragraph",
  "heading",
  "blockquote",
  "codeBlock",
  "bulletList",
  "orderedList",
  "taskList",
  "table",
  "horizontalRule",
  "markdownRaw",
  // A list is one block, but its items each carry their own slice — see the
  // note on `listToJson` in `document.ts`.
  "listItem",
  "taskItem",
];

/**
 * A block of markdown this editor does not model: a raw HTML block, a link
 * reference definition, a footnote definition.
 *
 * An atom holding its own text. Rendering it as live HTML would put the
 * document's markup inside the editor's own DOM, which is both unpickable and
 * a way to let a file's `<script>` at the app; printing the source says what
 * is there, keeps the bytes exact, and is the same choice the rest of the file
 * tab makes about content it cannot edit.
 */
const MarkdownRaw = Node.create({
  name: "markdownRaw",
  group: "block",
  atom: true,
  selectable: true,
  addAttributes() {
    return { text: { default: "" } };
  },
  parseHTML() {
    return [{ tag: "pre[data-markdown-raw]" }];
  },
  renderHTML({ node }) {
    return [
      "pre",
      {
        "data-markdown-raw": "",
        class:
          "my-4 overflow-x-auto rounded-md border border-dashed bg-muted/40 px-3 py-2 font-mono text-[12px] leading-relaxed text-muted-foreground",
      },
      node.attrs.text as string,
    ];
  },
});

/**
 * `mdSource` and `mdGap` on every block, and `mdAlign` on tables.
 *
 * `rendered: false` keeps them out of the DOM — they are the editor's memory
 * of the file, not part of the document's markup. `keepOnSplit: false` for
 * `mdSource` is belt and braces: a split block is a changed block either way,
 * because `document.ts` compares rather than trusts the flag.
 */
const SourceAttributes = Extension.create({
  name: "markdownSource",
  addGlobalAttributes() {
    return [
      {
        types: TOP_LEVEL,
        attributes: {
          mdSource: { default: null, rendered: false, keepOnSplit: false },
          mdGap: { default: null, rendered: false, keepOnSplit: true },
        },
      },
      {
        types: ["table"],
        attributes: { mdAlign: { default: null, rendered: false } },
      },
    ];
  },
});

export const markdownExtensions = [
  StarterKit.configure({
    // Markdown has no underline, and a document that can hold one is a
    // document that can be saved with it silently dropped.
    underline: false,
    link: { openOnClick: false, autolink: false },
    codeBlock: { languageClassPrefix: "language-" },
  }),
  // Inline, because in markdown an image is phrasing content: it lives in a
  // paragraph beside the text, and a block-level one cannot be written back.
  Image.configure({ inline: true, allowBase64: true }),
  TaskList,
  TaskItem.configure({ nested: true }),
  TableKit.configure({ table: { resizable: false } }),
  MarkdownRaw,
  SourceAttributes,
];
