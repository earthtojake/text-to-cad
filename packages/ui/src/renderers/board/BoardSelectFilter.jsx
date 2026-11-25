import { useI18n } from "@cad/ui/i18n";
import SelectFilterMenu from "../kit/tools/select/SelectFilterMenu.jsx";
import { BOARD_LOCKED, BOARD_SELECT_KINDS } from "./boardPick.js";

// Each box and KiCad's words for it: a box and its name, nothing more, as KiCad's Selection Filter.
const BOXES = Object.freeze({
  [BOARD_LOCKED]: "board.text.locked_items",
  parts: "board.text.footprints",
  texts: "board.text.texts",
  tracks: "board.text.tracks",
  vias: "board.text.vias",
  pads: "board.text.pads",
  graphics: "board.text.graphics",
  zones: "board.text.zones",
  ruleAreas: "board.text.rule_areas",
  dimensions: "board.text.dimensions",
});

/**
 * A board's Select filter: KiCad's Selection Filter, the kit's Filter (`kit/tools/select/SelectFilterMenu.jsx`):
 * one row, "Filter", whose submenu holds All, then the kinds in KiCad's order in one column
 * (`BOARD_SELECT_KINDS`: Footprints, Text, Tracks, Vias, Pads, Graphics, Zones, Rule areas,
 * Dimensions), each its name alone, then Locked items at the foot. Ticking one leaves the submenu open
 * and takes Select up. All ticks or unticks every kind, and is ticked when all are, a dash when some
 * are; Locked items is no kind: ticked, a click takes what KiCad saved locked too (unticked as a board
 * opens, as KiCad's), a modifier the chevron names after the kinds. The chevron's name says what is ticked
 * ("Filter: everything", "Filter: Pads", "Filter: everything, Locked items").
 *
 * @param {{ value: readonly string[], onChange(filter: readonly string[]): void, disabled?: boolean }} props
 */
export default function BoardSelectFilter({ value, onChange, disabled = false }) {
  const { t } = useI18n();
  return <SelectFilterMenu value={value} onChange={onChange} disabled={disabled}
    kinds={BOARD_SELECT_KINDS.map(id => ({ id, label: t(BOXES[id]) }))} extras={[{ id: BOARD_LOCKED, label: t(BOXES[BOARD_LOCKED]), modifier: true }]} />;
}
