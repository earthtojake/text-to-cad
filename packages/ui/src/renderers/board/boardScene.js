/**
 * A board as the kit's selection hook reads a scene (`kit/tools/select/useSceneSelection.js`): its
 * picks by board reference (`#R1`, `#R1.2`, `#net:VBUS`, `#net:VBUS@x10y5`, `#@x10y5`: what Quick
 * Edit names and `cadgen.pcb.read_board(path).resolve(ref)` reads), each described
 * (`boardFacts.js`), and its highlight, which `onHighlight` paints — what is hovered and selected,
 * resolved on this board.
 *
 * Importing this module has no environmental effects.
 */
import { describeBoardReference } from "./boardFacts.js";

/**
 * @param {ReturnType<typeof import("@text-to-cad/core/lib/board2d/boardIndex.js").createBoardIndex>} index
 * @param {{ onHighlight(ink: { hovered: object[], selected: object[] }): void }} options
 */
export function createBoardScene(index, { onHighlight, t }) {
  const resolved = ids => ids.map(id => index.resolve(id)).filter(Boolean);
  return {
    hasPart: id => Boolean(index.resolve(id)),
    describePart: id => describeBoardReference(index.resolve(id), index, t),
    setHighlight({ hovered = [], selected = [] } = {}) {
      onHighlight({ hovered: resolved(hovered), selected: resolved(selected) });
    }
  };
}
