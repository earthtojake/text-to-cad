import { useI18n } from "@cad/ui/i18n";
import { useMemo } from "react";
import CircuitTree from "../kit/inspector/CircuitTree.jsx";
import { NetKindIcon, PadKindIcon, PartKindIcon } from "./boardIcons.jsx";
import { boardTreeNodeIds, buildBoardTree } from "./boardTree.js";

// The Nets group's row (`boardTree.js`): shut as the tab opens.
const CLOSED = Object.freeze(["group:nets"]);
// A row's kind, in the glyphs Select's filter and the chips name the kinds with: a pad's copper, a part's body and legs, a net's trace.
const KIND_GLYPHS = Object.freeze({ part: PartKindIcon, pad: PadKindIcon, net: NetKindIcon });

/**
 * A board's **Circuit**, a tab of the view's panel (`boardTree.js`): its parts in blocks — the
 * schematic sheets their footprints record, else their kinds — each part with its pads, then its
 * nets, each with the pads on it, as the kit's Circuit tree draws one (`kit/inspector/CircuitTree.jsx`:
 * its filter, a part's reference, value, footprint name and MPN, a net's name; its rules for what opens,
 * what a press selects and frames, what a pick on the board reveals, and a part's or a net's eye). A
 * selected net is lit on the board, the rest stepped back, as KiCad's net highlight; the blocks and
 * "Nets (N)" open closed.
 *
 * @param {{ index: object, selection: ReturnType<typeof import("../kit/tools/select/useSceneSelection.js").useSceneSelection>,
 *   isolated: readonly string[], onIsolate(selector: string): void, onSelect(): void, onFrame?(selectors: readonly string[]): void }} props
 */
export default function BoardSection({ index, ...props }) {
  const { t } = useI18n();
  const tree = useMemo(() => buildBoardTree(index, t), [index, t]);
  const panel = useMemo(() => ({ listLabel: t("board.text.board_parts_and_nets"), treeLabel: t("board.text.board"), resultsLabel: t("board.text.board_search_results") }), [t]);
  return <CircuitTree tree={tree} nodeIdsOf={boardTreeNodeIds} glyphs={KIND_GLYPHS} closedGroups={CLOSED} data="board" panel={panel} {...props} />;
}
