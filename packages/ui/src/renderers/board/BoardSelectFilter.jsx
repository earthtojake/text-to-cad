import { useI18n } from "@cad/ui/i18n";
import SelectFilterMenu from "../kit/tools/select/SelectFilterMenu.jsx";
import { useControlUsage } from "../../usage/controls.js";
import { BOARD_FILTER_GRID, BOARD_LOCKED, BOARD_SELECT_KINDS, boardFilterAll, readBoardFilter } from "./boardPick.js";

// Each box and KiCad's words for it: a box and its name, nothing more, as KiCad's Selection Filter.
const BOXES = Object.freeze({
  all: "board.text.all_items",
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
// What telemetry counts of it (`usage/controls.js`): All items and Footprints, as the earlier menu's All and Parts.
const COUNTED = Object.freeze({ all: "select_filter_all", parts: "select_filter_parts" });

/**
 * A board's Select filter: KiCad's Selection Filter, the kit's filter menu (`kit/tools/select/SelectFilterMenu.jsx`),
 * a grid of boxes in its two columns, row by row (`BOARD_FILTER_GRID`) — All items and Locked items, then Footprints and Text, Tracks and Vias,
 * Pads and Graphics, Zones and Rule Areas, Dimensions — in the chevron's dropdown after Select's
 * button (`ToolSettingsMenu`), headed "Pick", each box a stock checkbox item, its name alone (no
 * glyph, as KiCad's boxes have none), its check at the row's right end as every menu's. Ticking one leaves the menu open and takes Select up. All items ticks
 * or unticks every kind, and is ticked when all are, a dash when some are; Locked items is no kind:
 * ticked, a click takes what KiCad saved locked too (unticked as a board opens, as KiCad's). The
 * chevron's name says what is ticked ("Selection filter: everything", "Selection filter: Pads").
 *
 * @param {{ value: readonly string[], onChange(filter: readonly string[]): void, disabled?: boolean }} props
 */
export default function BoardSelectFilter({ value, onChange, disabled = false }) {
  const { t } = useI18n();
  const controls = useControlUsage();
  const kinds = BOARD_SELECT_KINDS.filter(id => value.includes(id));
  const everything = boardFilterAll(value);
  const named = kinds.map(id => t(BOXES[id])).join(", ");
  const mode = everything ? t("select.everything") : named || t("board.text.nothing");
  const toggle = (id, on) => {
    if (COUNTED[id] && on) controls.used(COUNTED[id]);
    const locked = value.includes(BOARD_LOCKED) ? [BOARD_LOCKED] : [];
    if (id === "all") onChange(readBoardFilter(on ? [...BOARD_SELECT_KINDS, ...locked] : locked));
    else onChange(readBoardFilter(on ? [...value, id] : value.filter(other => other !== id)));
  };
  const checked = id => (id === "all" ? (everything ? true : kinds.length ? "indeterminate" : false) : value.includes(id));
  return <SelectFilterMenu grid={BOARD_FILTER_GRID} label={id => t(BOXES[id])} checked={checked} onToggle={toggle} mode={mode} disabled={disabled}
    trigger={everything ? "all" : kinds.join(" ") || "none"} />;
}
