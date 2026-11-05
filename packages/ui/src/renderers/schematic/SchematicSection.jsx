import { useI18n } from "@cad/ui/i18n";
import { useCallback, useMemo, useRef } from "react";
import CircuitDetail from "../kit/inspector/CircuitDetail.jsx";
import CircuitTree from "../kit/inspector/CircuitTree.jsx";
import { NetKindIcon, PinKindIcon, SymbolKindIcon } from "./schematicIcons.jsx";
import { buildSchematicTree, schematicDetail, schematicRowOwners, schematicTreeNodeIds } from "./schematicTree.js";

const CLOSED = Object.freeze(["group:unconnected"]);
const KIND_GLYPHS = Object.freeze({ part: SymbolKindIcon, pin: PinKindIcon, pad: PinKindIcon, net: NetKindIcon });

/** A schematic's lists, built once for both its tabs (`schematicTree.js`). */
export function useSchematicTrees(index) {
  const { t } = useI18n();
  return useMemo(() => (index ? buildSchematicTree(index, t) : null), [index, t]);
}

/**
 * A schematic's **Parts** or its **Nets** (`list`), each a tab of the view's panel (`schematicTree.js`):
 * its parts in blocks — the sheets they are placed on — each with its reference and value, or its nets,
 * as the kit's Circuit list draws one (`kit/inspector/CircuitTree.jsx`, a board's rules: open until
 * there is a choice, a block of several parts shut; only the chevron opens a row; a pick on the sheet
 * reveals its row, a press in the list reveals nothing). A press selects what the row names across the
 * hierarchy and shows it: the first sheet it is on, if it is not on the sheet shown (`onShow`); a
 * double-click frames it, there or on that sheet (`onFrame`). A selected net is lit on the sheet, the
 * rest stepped back, as KiCad's net highlight.
 *
 * @param {{ index: object, trees: ReturnType<typeof buildSchematicTree>, list: "parts" | "nets", selection: object,
 *   isolated: readonly string[], onIsolate(selector: string): void, onSelect(): void,
 *   onShow?(selectors: readonly string[]): void, onFrame?(selectors: readonly string[]): void }} props
 */
export default function SchematicSection({ index, trees, list, ...props }) {
  const { t } = useI18n();
  const parts = list === "parts";
  const panel = useMemo(() => ({ listLabel: t(parts ? "schematic.text.schematic_parts" : "schematic.text.schematic_nets"),
    treeLabel: t(parts ? "schematic.text.schematic_parts" : "schematic.text.schematic_nets"), resultsLabel: t("schematic.text.schematic_search_results") }), [t, parts]);
  const ownerOf = useCallback(selector => schematicRowOwners(index, selector), [index]);
  return <CircuitTree tree={parts ? trees.parts : trees.nets} searchRoots={parts ? trees.partsSearch : null} nodeIdsOf={schematicTreeNodeIds} ownerOf={ownerOf}
    glyphs={KIND_GLYPHS} closedGroups={CLOSED} data="schematic" panel={panel} {...props} />;
}

/**
 * What the schematic's selection picks, in detail under its lists (`kit/inspector/CircuitDetail.jsx`):
 * the last thing selected, or null when it is nothing a detail holds (the panel then draws none). A
 * row of the detail shown picked (a pad of the net shown) keeps that detail, as Altium's lists keep
 * the list above the one picked in.
 */
export function useSchematicDetail(index, selection, props) {
  const { t } = useI18n();
  const last = selection.selected.at(-1);
  const kept = useRef(null);
  const detail = useMemo(() => {
    if (!index || !last) return null;
    const shown = kept.current;
    return shown?.rows.some(row => row.pick === last) ? schematicDetail(index, shown.pick, t) : schematicDetail(index, last, t);
  }, [index, last, t]);
  kept.current = detail;
  return detail ? <CircuitDetail detail={detail} selection={selection} glyphs={KIND_GLYPHS} data="schematic" {...props} /> : null;
}
