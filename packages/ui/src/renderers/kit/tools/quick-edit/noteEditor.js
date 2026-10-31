import { promptReferenceIds } from "@text-to-cad/core/prompt";
import { referenceToken } from "./quickEditPrompt.js";
import { compactSuffix, hasPickGlyph, pickGlyphNode } from "../../inspector/pickGlyph.jsx";

// Quick Edit's note is plain text with references inline: an editable field whose text is the
// person's and whose chips are references pasted into it, each one atomic (a Backspace takes it
// whole) and read back as the reference it stands for (`/models/base.step#f:base.make_box1.2`), in its place.

// A chip's own size and look (`ReferenceChips.jsx`): 20px tall, its background, its glyph first,
// then its words. It is the note's 20px line, top to bottom, so it sits in the text's rows without
// spacing them out. Selected (`markSelectedPills`), it is highlighted as selected text is.
const CHIP_CLASS = "mx-px inline-flex h-5 cursor-default select-none items-center gap-1 whitespace-nowrap rounded-sm bg-accent/70 px-1.5 align-top text-tiny leading-5 text-foreground data-[selected]:bg-selection data-[selected]:text-selection-foreground data-[selected]:ring-1 data-[selected]:ring-primary";
const PILL = "[data-quick-edit-note-ref]";
const GLYPH_CLASS = "size-2.5 shrink-0";

/**
 * A pill in the note: atomic (a Backspace takes it whole) and read back as `token`, in its place;
 * shown as its chip is — its glyph (`kind`, coloured by `color`, else muted), then `text`, then
 * `suffix` (a pick's number or count), muted.
 */
function notePill(document, { token, kind = "", color = null, text, suffix = "" }) {
  const chip = document.createElement("span");
  chip.setAttribute("contenteditable", "false");
  chip.dataset.quickEditNoteRef = token;
  chip.className = CHIP_CLASS;
  if (hasPickGlyph(kind)) chip.append(pickGlyphNode(document, kind, color ? GLYPH_CLASS : `${GLYPH_CLASS} text-muted-foreground`, color));
  if (text) chip.append(text);
  if (suffix) {
    const muted = document.createElement("span");
    muted.className = "text-muted-foreground";
    muted.textContent = suffix;
    chip.append(muted);
  }
  chip.title = token;
  return chip;
}

/**
 * A reference as the note shows it: a pill carrying its token, named as the view names it — a
 * reference into the file on screen by what the renderer calls it (`name`: a part "cam", or a pick
 * by its part, kind and number, `{ name: "cam", kind: "face", number: "3" }`), into any other by its
 * file and what in it ("hinge.step · e:hinge.make_box1.4").
 */
export function noteChip(reference, document = globalThis.document, name = "") {
  const token = referenceToken(reference);
  if (name && typeof name === "object") {
    return notePill(document, { token, kind: name.kind, text: name.name || "", suffix: compactSuffix(name) });
  }
  const text = (typeof name === "string" && name) || `${reference.resource.path.split("/").pop()} · ${promptReferenceIds(reference).join(", ")}`;
  return notePill(document, { token, text });
}

/** An annotation (its annotation file's JSON, as its chip copies it) as the note shows it, named `text` (its chip's name). */
export function noteAnnotation(annotation, document = globalThis.document, text = "Annotation") {
  return notePill(document, { token: JSON.stringify(annotation), kind: "pencil", text });
}

/** The note as text: its words as written, each chip its reference's token, line breaks kept. */
export function noteText(root) {
  if (!root) return "";
  let text = "";
  const walk = node => {
    for (const child of node.childNodes) {
      if (child.nodeType === 3) text += child.nodeValue;
      else if (child.nodeType !== 1) continue;
      else if (child.dataset?.quickEditNoteRef) text += child.dataset.quickEditNoteRef;
      else if (child.tagName === "BR") text += "\n";
      else {
        // A block an editor wraps a line in starts a new line.
        if ((child.tagName === "DIV" || child.tagName === "P") && text && !text.endsWith("\n")) text += "\n";
        walk(child);
      }
    }
  };
  walk(root);
  return text.replace(/ /g, " ");
}

/**
 * A pill a click lands on, selected as a word is (the selection around it, so a Backspace, a Delete
 * or a key typed replaces it): the note's own, else null and the click is the editor's.
 */
export function selectPillAt(root, target) {
  const pill = target?.closest?.(PILL);
  if (!pill || !root?.contains(pill)) return null;
  const document = root.ownerDocument;
  const range = document.createRange();
  range.selectNode(pill);
  const selection = document.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  markSelectedPills(root);
  return pill;
}

/** Each pill the selection takes in marked `data-selected`, the rest unmarked: a pill shows no selection of its own. */
export function markSelectedPills(root) {
  if (!root) return;
  const selection = root.ownerDocument.getSelection?.();
  const range = selection?.rangeCount && !selection.isCollapsed ? selection.getRangeAt(0) : null;
  for (const pill of root.querySelectorAll(PILL)) {
    if (range?.intersectsNode(pill)) pill.dataset.selected = "";
    else delete pill.dataset.selected;
  }
}

/** Nodes put in at the caret (or at the end, where the caret is not in the note), the caret after them. */
export function insertAtCaret(root, nodes) {
  const document = root.ownerDocument;
  const selection = document.getSelection?.();
  let range = selection?.rangeCount ? selection.getRangeAt(0) : null;
  if (!range || !root.contains(range.commonAncestorContainer)) {
    range = document.createRange();
    range.selectNodeContents(root);
    range.collapse(false);
  }
  range.deleteContents();
  const fragment = document.createDocumentFragment();
  nodes.forEach(node => fragment.append(node));
  const last = fragment.lastChild;
  range.insertNode(fragment);
  if (last && selection) {
    const after = document.createRange();
    after.setStartAfter(last);
    after.collapse(true);
    selection.removeAllRanges();
    selection.addRange(after);
  }
}

/**
 * A paste as the note's nodes: each line that is a chip's copy alone (`pastedLines`: a reference or
 * the annotation) its pill, followed by a space to type on after it; every other line
 * text, the lines' breaks kept. `annotationName` names the annotation's pill, as its chip is named.
 */
export function pasteNodes(lines, document = globalThis.document, nameReference = null, annotationName = "Annotation") {
  const nodes = [];
  lines.forEach((line, index) => {
    if (index) nodes.push(document.createTextNode("\n"));
    if (typeof line === "string") { if (line) nodes.push(document.createTextNode(line)); return; }
    const pill = line.chip ? notePill(document, { token: line.token, kind: line.chip.glyph ?? line.chip.compact?.kind,
      color: line.chip.glyphColor, text: line.chip.text ?? line.chip.label })
      : line.annotation ? noteAnnotation(line.annotation, document, annotationName)
        : noteChip(line, document, nameReference?.(line) || "");
    nodes.push(pill, document.createTextNode(" "));
  });
  return nodes;
}
