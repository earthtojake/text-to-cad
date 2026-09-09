import { isCadFile, referenceText, splitReference, type CadReference } from "@shared/cad-refs";

/**
 * The composer's reference grammar and its document (plan §2, item 4c).
 *
 * The prompt a person is writing is text — the draft in the composer store,
 * what is sent, what the agent reads. A reference in it (`models/bracket.step#o1.2`,
 * `#label.f45`, `bracket.step`) is drawn as a chip while it is being edited
 * and goes back to those exact characters on send. So there are two shapes of
 * the same thing and two functions between them: `docFromText` builds the
 * editor's document from the draft, `textFromDoc` prints the draft from the
 * document. Both are pure JSON in and out, so the round trip is a unit test
 * and the editor is only ever a view of the draft.
 *
 * What counts as a reference while typing is stricter than what the
 * transcript links (`../links/grammar.ts`): a word is a chip when it carries a
 * selector (`#…` after a file, or bare) or is a CAD file by extension. A
 * `README.md` in a prompt stays words — the person is talking about it, not
 * pointing into it.
 */
export type Segment = { type: "text"; text: string } | { type: "reference"; reference: CadReference };

/** Punctuation a sentence hangs on a reference; kept as text after the chip. */
const TRAILING_RE = /[.,;:!?)\]]+$/;

/** Is this word, on its own, a reference? */
export function parseReference(word: string): CadReference | null {
  if (!word || /\s/.test(word) || word.includes("://")) {
    return null;
  }
  const split = splitReference(word);
  if (!split) {
    return null;
  }
  if (split.selector) {
    // `#o1` alone, or `<file>#o1` where the file half is a path, not a word
    // with a hash in it (`C#`, `issue#12`).
    return split.file === "" || isReferenceHost(split.file) ? split : null;
  }
  return isReferenceHost(split.file) ? split : null;
}

/** A file a reference can name: a CAD file, or the generator that makes one. */
function isReferenceHost(file: string): boolean {
  if (!file || file.startsWith("#") || /[<>"'`|]/.test(file)) {
    return false;
  }
  return isCadFile(file) || /\.(step|stp)\.py$/i.test(file);
}

/** Text into segments: words that are references become chips, the rest stays. */
export function parseSegments(text: string): Segment[] {
  const segments: Segment[] = [];
  let pending = "";
  const flush = () => {
    if (pending) {
      segments.push({ type: "text", text: pending });
      pending = "";
    }
  };
  // Split keeping the whitespace, so the text between chips is exact.
  for (const piece of text.split(/(\s+)/)) {
    if (!piece || /^\s+$/.test(piece)) {
      pending += piece;
      continue;
    }
    const trailing = TRAILING_RE.exec(piece)?.[0] ?? "";
    const word = piece.slice(0, piece.length - trailing.length);
    const reference = parseReference(word);
    if (!reference) {
      pending += piece;
      continue;
    }
    flush();
    segments.push({ type: "reference", reference });
    pending += trailing;
  }
  flush();
  return segments;
}

/** The chip's serialized form — what the agent reads. */
export const referenceToken = referenceText;

/* -------------------------------------------------------------------------- */
/* The editor's document                                                       */
/* -------------------------------------------------------------------------- */

/** ProseMirror JSON, as far as this editor uses it. */
export type DocNode = {
  type: string;
  attrs?: Record<string, unknown>;
  content?: DocNode[];
  text?: string;
};

export const REFERENCE_NODE = "reference";

export function referenceNode(reference: CadReference): DocNode {
  return { type: REFERENCE_NODE, attrs: { file: reference.file, selector: reference.selector } };
}

/** One paragraph's content: text, chips and hard breaks, from a string. */
export function inlineContentFromText(text: string): DocNode[] {
  const content: DocNode[] = [];
  const lines = text.split("\n");
  lines.forEach((line, index) => {
    if (index > 0) {
      content.push({ type: "hardBreak" });
    }
    for (const segment of parseSegments(line)) {
      if (segment.type === "text") {
        if (segment.text) {
          content.push({ type: "text", text: segment.text });
        }
      } else {
        content.push(referenceNode(segment.reference));
      }
    }
  });
  return content;
}

/**
 * The whole document: one paragraph. Newlines are hard breaks — the
 * textarea's model, which is what Enter-sends and Shift+Enter-breaks need.
 */
export function docFromText(text: string): DocNode {
  return { type: "doc", content: [{ type: "paragraph", content: inlineContentFromText(text) }] };
}

/** The draft back out of the document, chips as their tokens. */
export function textFromDoc(doc: DocNode | null | undefined): string {
  const out: string[] = [];
  const walk = (node: DocNode, depth: number) => {
    switch (node.type) {
      case "text":
        out.push(node.text ?? "");
        return;
      case "hardBreak":
        out.push("\n");
        return;
      case REFERENCE_NODE:
        out.push(referenceToken({ file: String(node.attrs?.file ?? ""), selector: String(node.attrs?.selector ?? "") }));
        return;
      default:
        break;
    }
    // A second paragraph (a paste of two, before the schema flattens it) is a
    // newline apart from the first.
    if (node.type === "paragraph" && out.length > 0 && depth > 0) {
      out.push("\n");
    }
    for (const child of node.content ?? []) {
      walk(child, depth + 1);
    }
  };
  if (doc) {
    walk(doc, 0);
  }
  return out.join("");
}
