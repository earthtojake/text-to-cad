import { useI18n } from "@cad/ui/i18n";
import SelectFilterMenu from "../kit/tools/select/SelectFilterMenu.jsx";
import { SCHEMATIC_FILTER_GRID, SCHEMATIC_SELECT_KINDS, readSchematicFilter } from "./tools.js";

const BOXES = Object.freeze({
  all: "board.text.all_items", symbols: "schematic.text.symbols", pins: "schematic.text.pins", wires: "schematic.text.wires",
  labels: "schematic.text.labels", sheets: "schematic.text.sheets", other: "schematic.text.other_items"
});

/**
 * A schematic's Select filter: KiCad's Selection Filter, the kit's filter menu
 * (`kit/tools/select/SelectFilterMenu.jsx`) — All items, then Symbols and Pins, Wires and Labels, Sheets
 * and Other items (junctions, no-connects) — each box a checkbox and its name, no glyph. Ticking one
 * leaves the menu open and takes Select up; All items ticks or unticks every kind, a dash when some are.
 *
 * @param {{ value: readonly string[], onChange(filter: readonly string[]): void, disabled?: boolean }} props
 */
export default function SchematicSelectFilter({ value, onChange, disabled = false }) {
  const { t } = useI18n();
  const kinds = SCHEMATIC_SELECT_KINDS.filter(id => value.includes(id));
  const everything = kinds.length === SCHEMATIC_SELECT_KINDS.length;
  const mode = everything ? t("select.everything") : kinds.map(id => t(BOXES[id])).join(", ") || t("board.text.nothing");
  const toggle = (id, on) => {
    if (id === "all") onChange(on ? SCHEMATIC_SELECT_KINDS : []);
    else onChange(readSchematicFilter(on ? [...value, id] : value.filter(other => other !== id)));
  };
  const checked = id => (id === "all" ? (everything ? true : kinds.length ? "indeterminate" : false) : value.includes(id));
  return <SelectFilterMenu grid={SCHEMATIC_FILTER_GRID} label={id => t(BOXES[id])} checked={checked} onToggle={toggle} mode={mode} disabled={disabled}
    trigger={everything ? "all" : kinds.join(" ") || "none"} data="schematic" />;
}
