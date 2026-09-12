import { InputRule, Node, mergeAttributes } from "@tiptap/core";
import { NodeSelection } from "@tiptap/pm/state";
import { ReactNodeViewRenderer } from "@tiptap/react";

import type { CadReference } from "@shared/cad-refs";

import { ReferenceChip } from "./ReferenceChip";
import { REFERENCE_NODE, parseSegments, referenceToken } from "./references";

/**
 * A CAD reference as an inline atom in the composer's document.
 *
 * An atom, so the editor treats it as one character: the arrow keys step
 * over it and select it as a unit (ProseMirror's NodeSelection, drawn as a
 * ring by `ReferenceChip`), and Delete on the selected chip removes it.
 * Backspace right after it removes the whole chip — ProseMirror's own
 * Backspace would *select* the atom first and delete it on the second
 * press, which reads as a chip that will not go away, so the keymap below
 * deletes it outright (and Delete before it, the same). It carries the two halves of the
 * reference as attributes and prints back to `file#selector` through
 * `renderText`, which is what the clipboard gets when a chip is copied out.
 *
 * The input rule is how typing makes one: a word that parses as a
 * reference (`references.ts`) becomes a chip the moment the space after it
 * is typed, the space kept, any punctuation the word carried (`#o1.2,`)
 * left as text after the chip. Pasting goes through `docFromText` in the
 * editor rather than a paste rule, because a paste can hold several lines
 * and a paste rule sees one match at a time.
 */
export const ReferenceNode = Node.create({
  name: REFERENCE_NODE,
  group: "inline",
  inline: true,
  atom: true,
  selectable: true,
  draggable: false,

  addAttributes() {
    return {
      file: { default: "" },
      selector: { default: "" },
    };
  },

  parseHTML() {
    return [
      {
        tag: "span[data-reference-chip]",
        getAttrs: (element) => ({
          file: element.getAttribute("data-file") ?? "",
          selector: element.getAttribute("data-selector") ?? "",
        }),
      },
    ];
  },

  renderHTML({ node, HTMLAttributes }) {
    const reference = node.attrs as CadReference;
    return [
      "span",
      mergeAttributes(HTMLAttributes, {
        "data-reference-chip": "",
        "data-file": reference.file,
        "data-selector": reference.selector,
      }),
      referenceToken(reference),
    ];
  },

  renderText({ node }) {
    return referenceToken(node.attrs as CadReference);
  },

  addNodeView() {
    return ReactNodeViewRenderer(ReferenceChip);
  },

  addKeyboardShortcuts() {
    const removeAdjacent = (direction: "before" | "after") => () => {
      const { selection } = this.editor.state;
      if (selection instanceof NodeSelection && selection.node.type === this.type) {
        return this.editor.commands.deleteSelection();
      }
      if (!selection.empty) {
        return false;
      }
      const $pos = selection.$from;
      const neighbour = direction === "before" ? $pos.nodeBefore : $pos.nodeAfter;
      if (!neighbour || neighbour.type !== this.type) {
        return false;
      }
      const from = direction === "before" ? $pos.pos - neighbour.nodeSize : $pos.pos;
      return this.editor.commands.deleteRange({ from, to: from + neighbour.nodeSize });
    };
    return { Backspace: removeAdjacent("before"), Delete: removeAdjacent("after") };
  },

  addInputRules() {
    const type = this.type;
    return [
      new InputRule({
        // The word before the space just typed. `range.to` is where the
        // space would go; the word ends there.
        find: /(?:^|\s)(\S+)\s$/,
        // Not undoable: TipTap's Backspace would otherwise turn a chip just
        // made back into its text, which reads as the chip refusing to be
        // deleted. Backspace deletes the space, then the chip (the keymap).
        undoable: false,
        handler: ({ state, range, match }) => {
          const word = match[1] ?? "";
          const segments = parseSegments(word);
          const first = segments[0];
          if (!word || first?.type !== "reference") {
            return null;
          }
          const trailing = segments[1]?.type === "text" ? segments[1].text : "";
          // Typed, the space is not in the document yet and `range.to` is
          // where it goes; simulated (`insertContent` with input rules, the
          // tests), the whole string is already there and `range.to` is past
          // the space. The word's place is the match's, either way.
          const wordStart = range.from + match[0].lastIndexOf(word);
          const wordEnd = wordStart + word.length;
          const spaceInDoc = range.to > wordEnd;
          const nodes = [
            type.create({ file: first.reference.file, selector: first.reference.selector }),
            ...(trailing || !spaceInDoc ? [state.schema.text(`${trailing}${spaceInDoc ? "" : " "}`)] : []),
          ];
          state.tr.replaceWith(wordStart, wordEnd, nodes).scrollIntoView();
          return undefined;
        },
      }),
    ];
  },
});
