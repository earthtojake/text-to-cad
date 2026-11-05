import { useI18n } from "@cad/ui/i18n";
import { useCallback, useMemo, useRef } from "react";
import CircuitDetail from "../kit/inspector/CircuitDetail.jsx";
import CircuitTree from "../kit/inspector/CircuitTree.jsx";
import { NetKindIcon, PadKindIcon, PartKindIcon } from "./boardIcons.jsx";
import { boardDetail, boardRowOwners, boardTreeNodeIds, buildBoardTree } from "./boardTree.js";

// The pins on nothing (`boardTree.js`): shut as the tab opens.
const CLOSED = Object.freeze(["group:unconnected"]);
// A row's kind, in the glyphs Select's filter and the chips name the kinds with: a pad's copper, a part's body and legs, a net's trace.
const KIND_GLYPHS = Object.freeze({ part: PartKindIcon, pad: PadKindIcon, net: NetKindIcon });

/** A board's lists, built once for both its tabs (`boardTree.js`). */
export function useBoardTrees(index) {
  const { t } = useI18n();
  return useMemo(() => (index ? buildBoardTree(index, t) : null), [index, t]);
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

/**
 * What the board's selection picks, in detail under its lists (`kit/inspector/CircuitDetail.jsx`):
 * the last thing selected, or null when it is nothing a detail holds (the panel then draws none). A
 * row of the detail shown picked (a pad of the net shown) keeps that detail, as Altium's lists keep
 * the list above the one picked in.
 */
export function useBoardDetail(index, selection, props) {
  const { t } = useI18n();
  const last = selection.selected.at(-1);
  const kept = useRef(null);
  const detail = useMemo(() => {
    if (!index || !last) return null;
    const shown = kept.current;
    return shown?.rows.some(row => row.pick === last) ? boardDetail(index, shown.pick, t) : boardDetail(index, last, t);
  }, [index, last, t]);
  kept.current = detail;
  return detail ? <CircuitDetail detail={detail} selection={selection} glyphs={KIND_GLYPHS} data="board" {...props} /> : null;
}
