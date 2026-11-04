import { useI18n } from "@cad/ui/i18n";
import { CircuitBoard } from "lucide-react";
import { useMemo } from "react";
import CircuitTree from "../kit/inspector/CircuitTree.jsx";
import { NetKindIcon, PinKindIcon, SymbolKindIcon } from "./schematicIcons.jsx";
import { buildSchematicTree, schematicTreeNodeIds } from "./schematicTree.js";

const CLOSED = Object.freeze(["group:nets"]);
const KIND_GLYPHS = Object.freeze({ part: SymbolKindIcon, pin: PinKindIcon, pad: PinKindIcon, net: NetKindIcon });

/**
 * A schematic's **Circuit**, a tab of the file sidebar (`schematicTree.js`): its parts in blocks — the
 * sheets they are placed on — each with its reference, value and pins, then its nets, each with the pins
 * on it, as the kit's Circuit tree draws one (`kit/inspector/CircuitTree.jsx`, a board's rules: open
 * until there is a choice, a block of several parts and the Nets shut; only the chevron opens a row; a
 * pick on the sheet reveals its row, a press in the tree reveals nothing). A press selects what the row
 * names across the hierarchy and shows it: on the sheet shown if it is there, else the first sheet it is
 * on (`onFrame`). A selected net is lit on the sheet, the rest stepped back, as KiCad's net highlight.
 *
 * @param {{ index: object, selection: object, isolated: readonly string[], onIsolate(selector: string): void, onSelect(): void,
 *   onFrame?(selectors: readonly string[]): void }} props
 */
export default function SchematicSection({ index, ...props }) {
  const { t } = useI18n();
  const tree = useMemo(() => buildSchematicTree(index, t), [index, t]);
  const panel = useMemo(() => ({
    id: "schematic", label: t("board.text.circuit"), icon: CircuitBoard, filterLabel: t("board.text.filter_circuit"),
    listLabel: t("schematic.text.schematic_parts_and_nets"), treeLabel: t("schematic.text.schematic"), resultsLabel: t("schematic.text.schematic_search_results"),
    nothingMatches: query => t("schematic.text.nothing_in_the_schematic_matches_query", { query })
  }), [t]);
  return <CircuitTree tree={tree} nodeIdsOf={schematicTreeNodeIds} glyphs={KIND_GLYPHS} closedGroups={CLOSED} data="schematic" panel={panel} {...props} />;
}
