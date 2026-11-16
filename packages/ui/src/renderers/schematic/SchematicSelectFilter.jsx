import { useI18n } from "@cad/ui/i18n";
import SelectFilterMenu from "../kit/tools/select/SelectFilterMenu.jsx";
import { SCHEMATIC_SELECT_KINDS } from "./tools.js";

const BOXES = Object.freeze({
  symbols: "schematic.text.symbols", pins: "schematic.text.pins", wires: "schematic.text.wires",
  labels: "schematic.text.labels", sheets: "schematic.text.sheets", other: "schematic.text.other_items"
});

/**
 * A schematic's Select filter: KiCad's Selection Filter, the kit's Filter
 * (`kit/tools/select/SelectFilterMenu.jsx`): one row, "Filter", whose submenu holds All, then Symbols,
 * Pins, Wires, Labels, Sheets and Other items (junctions, no-connects) in one column, each a checkbox and
 * its name, and no extras. Ticking one leaves the submenu open and takes Select up; All ticks or unticks
 * every kind, a dash when some are.
 *
 * @param {{ value: readonly string[], onChange(filter: readonly string[]): void, disabled?: boolean }} props
 */
export default function SchematicSelectFilter({ value, onChange, disabled = false }) {
  const { t } = useI18n();
  return <SelectFilterMenu value={value} onChange={onChange} disabled={disabled}
    kinds={SCHEMATIC_SELECT_KINDS.map(id => ({ id, label: t(BOXES[id]) }))} />;
}
