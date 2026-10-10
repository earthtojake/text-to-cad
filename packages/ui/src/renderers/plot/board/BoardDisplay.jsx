import { RotateCcw } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { FileSheetCheckboxRow, FileSheetSelectRow, FileSheetSettingsSection } from "../../kit/inspector/FileSheet.js";

/**
 * A board's Display settings: its Mode, which side it is seen from (the bottom mirrored, its layers
 * on top) and whether copper pours are filled — a pour hides the tracks under it, and a person
 * reading the routing turns it off. Modes are presets, as a 3D view's are (`render-mode.md`): each
 * says which layers are drawn and whether pours are filled, and a setting changed away from its
 * mode reads as Custom, the mode kept as what Reset returns to. The side is not a preset's, as a
 * 3D view's camera is not. KiCad still draws every layer; a mode only chooses among them.
 * Placement draws no copper: the parts, their pads and courtyards, and every connection as an
 * airwire (`boardAirwires`), routed or not — the board as it is laid out, before it is wired. A
 * net its pours join shows its airwires only when selected.
 * Kept with the file's view, as a 3D file's Display settings are.
 */
export const BOARD_DISPLAY_DEFAULTS = Object.freeze({ side: "top", mode: "board", poured: true });
const SIDES = [{ value: "top", label: "Top" }, { value: "bottom", label: "Bottom" }];

const icon = (children) => function BoardModeIcon(props) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" {...props}>{children}</svg>;
};
// Board: the outline with a part on it. Copper: two pads joined by a trace. Assembly: a part's
// body and legs in its dashed courtyard. Placement: two pads and the straight airwire between them.
export const BoardModeIcon = icon(<><rect x="3" y="5" width="18" height="14" rx="3" /><rect x="9" y="9.5" width="6" height="5" rx="0.8" /></>);
export const CopperModeIcon = icon(<><rect x="3" y="14" width="6" height="6" rx="1" fill="currentColor" /><rect x="15" y="4" width="6" height="6" rx="1" fill="currentColor" /><path d="M9 17h3l3-7" /></>);
export const AssemblyModeIcon = icon(<><rect x="3" y="3" width="18" height="18" rx="2" strokeDasharray="2.5 2.5" /><rect x="9" y="7.5" width="6" height="9" rx="0.8" /><path d="M6.5 10H9M6.5 14H9M15 10h2.5M15 14h2.5" /></>);
export const PlacementModeIcon = icon(<><rect x="3" y="14" width="6" height="6" rx="1" /><rect x="15" y="4" width="6" height="6" rx="1" /><path d="M9 14l6-4" strokeDasharray="2 2.2" /></>);

export const BOARD_MODE_OPTIONS = Object.freeze([
  Object.freeze({ value: "board", label: "Board", title: "Every layer, as the board is made", Icon: BoardModeIcon }),
  Object.freeze({ value: "copper", label: "Copper", title: "Copper only: tracks, pads, vias and pours", Icon: CopperModeIcon }),
  Object.freeze({ value: "assembly", label: "Assembly", title: "Silkscreen, fab outlines and courtyards: what is placed where", Icon: AssemblyModeIcon }),
  Object.freeze({ value: "placement", label: "Placement", title: "Parts, pads and courtyards with their connections as airwires, before routing", Icon: PlacementModeIcon }),
]);
// What each mode draws, by layer kind (the outline always), and its pours. `airwires`: the overlay
// draws the pads, their holes and every connection as a straight line, over a plot without copper
// or drills (KiCad's drill layer holds the vias' holes too, and a via is routing).
const MODES = Object.freeze({
  board: { kinds: ["copper", "silk", "fab", "drill", "outline", "ratsnest"], poured: true, airwires: false },
  copper: { kinds: ["copper", "drill", "outline", "ratsnest"], poured: true, airwires: false },
  assembly: { kinds: ["silk", "fab", "courtyard", "drill", "outline", "ratsnest"], poured: true, airwires: false },
  placement: { kinds: ["fab", "courtyard", "outline"], poured: true, airwires: true },
});
// Before modes a display named its layers (`all`, `copper`, `assembly`); `all` is Board.
const LEGACY_LAYERS = Object.freeze({ all: "board", copper: "copper", assembly: "assembly" });

/** A stored display, or the defaults where it says nothing usable. */
export function readBoardDisplay(raw) {
  const value = raw && typeof raw === "object" ? raw : {};
  const mode = MODES[value.mode] ? value.mode : LEGACY_LAYERS[value.layers] || "board";
  return {
    side: value.side === "bottom" ? "bottom" : "top",
    mode,
    poured: typeof value.poured === "boolean" ? value.poured : MODES[mode].poured,
  };
}

/** Whether a display has left its mode's preset (the side is not a preset's). */
export const boardDisplayIsCustom = (display) => display.poured !== MODES[display.mode].poured;

/** The display's mode chosen: its preset's values, the side kept. */
export const selectBoardMode = (display, mode) => ({ side: display.side, mode, poured: MODES[mode].poured });

/** Whether a display draws the board's airwires and pads itself (its plot without copper). */
export const boardDisplayAirwires = (display) => Boolean(display && MODES[display.mode].airwires);

/** The drawing's view for a display: the layer ids to draw (null = all), pours, side. */
export function boardDrawView(display, sheet) {
  const kinds = MODES[display.mode].kinds;
  const layers = Array.isArray(sheet?.layers) ? sheet.layers.filter((layer) => kinds.includes(layer.kind)).map((layer) => layer.id) : null;
  return { layers, poured: display.poured, side: display.side };
}

export function BoardDisplaySection({ display, onChange }) {
  const custom = boardDisplayIsCustom(display);
  const changed = custom || display.side !== BOARD_DISPLAY_DEFAULTS.side || display.mode !== BOARD_DISPLAY_DEFAULTS.mode;
  const selected = BOARD_MODE_OPTIONS.find((option) => option.value === display.mode) || BOARD_MODE_OPTIONS[0];
  const ModeIcon = selected.Icon;
  const drawsCopper = MODES[display.mode].kinds.includes("copper");
  return <FileSheetSettingsSection title="Display" sectionId="board"
    headingAction={changed ? <TooltipHint content="Reset board display"><Button type="button" variant="ghost" size="icon-xs" aria-label="Reset board display"
      className="size-6 text-muted-foreground hover:text-foreground" onClick={() => onChange({ ...BOARD_DISPLAY_DEFAULTS })}>
      <RotateCcw className="size-3" aria-hidden="true" /></Button></TooltipHint> : null}>
    <FileSheetSelectRow label="Mode" value={custom ? "" : selected.value} placeholder="Custom"
      onValueChange={(mode) => onChange(selectBoardMode(display, mode))}
      triggerContent={custom ? undefined : <span className="flex min-w-0 items-center gap-1"><ModeIcon className="size-3 shrink-0" aria-hidden="true" /><span className="truncate">{selected.label}</span></span>}
      triggerClassName="gap-1 px-1.5 [&_svg]:size-3"
      options={BOARD_MODE_OPTIONS.map(({ Icon, ...option }) => ({ ...option, icon: <Icon className="size-3.5" aria-hidden="true" /> }))} />
    <FileSheetSelectRow label="View from" value={display.side} options={SIDES} onValueChange={(side) => onChange({ ...display, side })} />
    {drawsCopper ? <FileSheetCheckboxRow label="Copper pours" checked={display.poured} onCheckedChange={(poured) => onChange({ ...display, poured })} /> : null}
  </FileSheetSettingsSection>;
}
