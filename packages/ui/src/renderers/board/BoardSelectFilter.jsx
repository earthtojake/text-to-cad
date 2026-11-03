import { Lock } from "lucide-react";
import { useI18n } from "@cad/ui/i18n";
import { DropdownMenuCheckboxItem, DropdownMenuLabel } from "@cad/ui/primitives/dropdown-menu";
import { ToolSettingsMenu } from "../kit/tools/ToolModeMenu.jsx";
import { modeGlyphIcon } from "../kit/tools/select/modeGlyphs.jsx";
import { useControlUsage } from "../../usage/controls.js";
import {
  DimensionKindIcon, GraphicKindIcon, PadKindIcon, PartKindIcon, RuleAreaKindIcon, TextKindIcon, TrackKindIcon, ViaKindIcon, ZoneKindIcon
} from "./boardIcons.jsx";
import { BOARD_FILTER_GRID, BOARD_LOCKED, BOARD_SELECT_KINDS, boardFilterAll, readBoardFilter } from "./boardPick.js";

// Each box, KiCad's words for it, and its glyph (the chips' own).
const ICON_CLASS = "size-3.5";
const BOXES = Object.freeze({
  all: { key: "board.text.all_items", icon: modeGlyphIcon("all") },
  [BOARD_LOCKED]: { key: "board.text.locked_items", icon: <Lock className={ICON_CLASS} aria-hidden="true" /> },
  parts: { key: "board.text.footprints", Icon: PartKindIcon },
  texts: { key: "board.text.texts", Icon: TextKindIcon },
  tracks: { key: "board.text.tracks", Icon: TrackKindIcon },
  vias: { key: "board.text.vias", Icon: ViaKindIcon },
  pads: { key: "board.text.pads", Icon: PadKindIcon },
  graphics: { key: "board.text.graphics", Icon: GraphicKindIcon },
  zones: { key: "board.text.zones", Icon: ZoneKindIcon },
  ruleAreas: { key: "board.text.rule_areas", Icon: RuleAreaKindIcon },
  dimensions: { key: "board.text.dimensions", Icon: DimensionKindIcon },
});
// What telemetry counts of it (`usage/controls.js`): All items and Footprints, as the earlier menu's All and Parts.
const COUNTED = Object.freeze({ all: "select_filter_all", parts: "select_filter_parts" });

/**
 * A board's Select filter: KiCad's Selection Filter, a grid of boxes in its two columns, row by row
 * (`BOARD_FILTER_GRID`) — All items and Locked items, then Footprints and Text, Tracks and Vias,
 * Pads and Graphics, Zones and Rule Areas, Dimensions — in the chevron's dropdown after Select's
 * button (`ToolSettingsMenu`), headed "Pick", each box a stock checkbox item, its check at the row's
 * right end as every menu's. Ticking one leaves the menu open and takes Select up. All items ticks
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
  const named = kinds.map(id => t(BOXES[id].key)).join(", ");
  const mode = everything ? t("select.everything") : named || t("board.text.nothing");
  const toggle = (id, on) => {
    if (COUNTED[id] && on) controls.used(COUNTED[id]);
    const locked = value.includes(BOARD_LOCKED) ? [BOARD_LOCKED] : [];
    if (id === "all") onChange(readBoardFilter(on ? [...BOARD_SELECT_KINDS, ...locked] : locked));
    else onChange(readBoardFilter(on ? [...value, id] : value.filter(other => other !== id)));
  };
  const checked = id => (id === "all" ? (everything ? true : kinds.length ? "indeterminate" : false) : value.includes(id));
  return <ToolSettingsMenu label={t("select.filter")} trigger="chevron" disabled={disabled} contentClassName="w-auto"
    triggerLabel={t("select.filterCurrent", { filter: t("select.filter"), mode })}
    triggerProps={{ "data-select-filter-trigger": everything ? "all" : kinds.join(" ") || "none" }}>
    <DropdownMenuLabel className="text-tiny font-normal text-muted-foreground">{t("select.pick")}</DropdownMenuLabel>
    <div className="grid grid-cols-2 gap-x-1" data-board-filter-grid="">
      {BOARD_FILTER_GRID.flat().map(id => {
        const { key, icon, Icon } = BOXES[id];
        return <DropdownMenuCheckboxItem key={id} checked={checked(id)} data-select-filter={id}
          onSelect={event => event.preventDefault()} onCheckedChange={on => toggle(id, on === true)}>
          {icon || <Icon className={ICON_CLASS} />}{t(key)}
        </DropdownMenuCheckboxItem>;
      })}
    </div>
  </ToolSettingsMenu>;
}
