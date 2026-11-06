import { useI18n } from "@cad/ui/i18n";
import { useCallback, useMemo } from "react";
import CircuitTree from "../kit/inspector/CircuitTree.jsx";
import { NetKindIcon, PadKindIcon, PartKindIcon } from "./boardIcons.jsx";
import { NO_MODEL_BLOCK, boardRowOwners, boardTreeNodeIds, buildBoardTree } from "./boardTree.js";

// The pins on nothing and the parts with no 3D model (`boardTree.js`): shut as the tab opens.
const CLOSED = Object.freeze(["group:unconnected", NO_MODEL_BLOCK]);
// A row's kind, in the glyphs Select's filter and the chips name the kinds with: a pad's copper, a part's body and legs, a net's trace.
const KIND_GLYPHS = Object.freeze({ part: PartKindIcon, pad: PadKindIcon, net: NetKindIcon });

/** A board's lists, built once for both its tabs (`boardTree.js`), the Parts' No 3D model block once its models table is in. */
export function useBoardTrees(index, models = null) {
  const { t } = useI18n();
  return useMemo(() => (index ? buildBoardTree(index, t, models) : null), [index, t, models]);
}

/**
 * A board's **Parts** or its **Nets** (`list`), each a tab of the view's panel (`boardTree.js`): its
 * parts in blocks — the schematic sheets their footprints record, else their kinds — or its nets,
 * as the kit's Circuit list draws one (`kit/inspector/CircuitTree.jsx`: its search, a part's reference,
 * value, footprint name and MPN, a pad's number and name, a net's name; its rules for what opens, what a
 * press selects and a double-click frames, what a pick on the board reveals, and a part's or a net's
 * eye). A selected net is lit on the board, the rest stepped back, as KiCad's net highlight; the
 * blocks of several parts and the pins on nothing open shut.
 *
 * @param {{ index: object, trees: ReturnType<typeof buildBoardTree>, list: "parts" | "nets",
 *   selection: ReturnType<typeof import("../kit/tools/select/useSceneSelection.js").useSceneSelection>,
 *   isolated: readonly string[], onIsolate(selector: string): void, onSelect(): void, onFrame?(selectors: readonly string[]): void }} props
 */
export default function BoardSection({ index, trees, list, ...props }) {
  const { t } = useI18n();
  const parts = list === "parts";
  const panel = useMemo(() => ({ listLabel: t(parts ? "board.text.board_parts" : "board.text.board_nets"), treeLabel: t(parts ? "board.text.board_parts" : "board.text.board_nets"),
    resultsLabel: t("board.text.board_search_results") }), [t, parts]);
  const ownerOf = useCallback(selector => boardRowOwners(index, selector), [index]);
  return <CircuitTree tree={parts ? trees.parts : trees.nets} searchRoots={parts ? trees.partsSearch : null} nodeIdsOf={boardTreeNodeIds} ownerOf={ownerOf}
    glyphs={KIND_GLYPHS} closedGroups={CLOSED} data="board" panel={panel} {...props} />;
}
