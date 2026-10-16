import { RotateCcw } from "lucide-react";
import {
  BOARD_DISPLAY_DEFAULTS, boardDisplayDrawsCopper, boardDisplayIsCustom, boardDisplayLayers, boardLayerGroups, readBoardDisplay,
  selectBoardMode, toggleBoardLayer,
} from "@text-to-cad/core/lib/plot2d/index.js";
import { Button } from "@text-to-cad/ui/primitives/button";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { FileSheetCheckboxRow, FileSheetSelectRow, FileSheetSettingsSection } from "../../kit/inspector/FileSheet.js";

/**
 * A board's Display settings (`settings-ui.md`, "A KiCad board"): two sections, always open.
 * **Display** is its Mode, which side it is seen from (the bottom mirrored, its layers on top) and
 * whether copper pours are filled — a pour hides the tracks under it, and a person reading the
 * routing turns it off. **Layers** is a checkbox per layer the payload holds, grouped front,
 * inner, back and other (the outline, the user layers, then the vias, the ratsnest and the
 * drills). Modes are presets, as a 3D view's are (`render-mode.md`): each is a layer set with its
 * pours, and a checkbox or the pours changed from the mode's reads as Custom, the mode kept as what
 * Reset returns to. The side is not a preset's, as a 3D view's camera is not.
 *
 * The contract — `{ mode, side, poured, layers }` — is core's (`plot2d/boardDisplay.js`), shared
 * with the headless snapshot, so what is drawn here is drawn there. Kept with the file's view, as
 * a 3D file's Display settings are.
 */
export { BOARD_DISPLAY_DEFAULTS, readBoardDisplay };
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

/**
 * @param {{ display: ReturnType<typeof readBoardDisplay>, onChange: (display: object) => void,
 *   sheet: { layers: { id: string, kind: string, side: string }[] } | null }} props
 *   `sheet`: the plot's, whose layers the checkboxes are; null until the plot is in (no Layers then).
 */
export function BoardDisplaySection({ display, onChange, sheet = null }) {
  const custom = boardDisplayIsCustom(display, sheet);
  const changed = custom || display.side !== BOARD_DISPLAY_DEFAULTS.side || display.mode !== BOARD_DISPLAY_DEFAULTS.mode;
  const selected = BOARD_MODE_OPTIONS.find((option) => option.value === display.mode) || BOARD_MODE_OPTIONS[0];
  const ModeIcon = selected.Icon;
  const drawn = new Set(boardDisplayLayers(display, sheet));
  const groups = boardLayerGroups(sheet);
  return <>
    <FileSheetSettingsSection title="Display" sectionId="board"
      headingAction={changed ? <TooltipHint content="Reset board display"><Button type="button" variant="ghost" size="icon-xs" aria-label="Reset board display"
        className="size-6 text-muted-foreground hover:text-foreground" onClick={() => onChange({ ...BOARD_DISPLAY_DEFAULTS })}>
        <RotateCcw className="size-3" aria-hidden="true" /></Button></TooltipHint> : null}>
      <FileSheetSelectRow label="Mode" value={custom ? "" : selected.value} placeholder="Custom"
        onValueChange={(mode) => onChange(selectBoardMode(display, mode))}
        triggerContent={custom ? undefined : <span className="flex min-w-0 items-center gap-1"><ModeIcon className="size-3 shrink-0" aria-hidden="true" /><span className="truncate">{selected.label}</span></span>}
        triggerClassName="gap-1 px-1.5 [&_svg]:size-3"
        options={BOARD_MODE_OPTIONS.map(({ Icon, ...option }) => ({ ...option, icon: <Icon className="size-3.5" aria-hidden="true" /> }))} />
      <FileSheetSelectRow label="View from" value={display.side} options={SIDES} onValueChange={(side) => onChange({ ...display, side })} />
      {boardDisplayDrawsCopper(display, sheet) ? <FileSheetCheckboxRow label="Copper pours" checked={display.poured} onCheckedChange={(poured) => onChange({ ...display, poured })} /> : null}
    </FileSheetSettingsSection>
    {groups.length ? <FileSheetSettingsSection title="Layers" sectionId="board-layers">
      <div className="flex flex-col gap-1" data-board-layers="">
        {groups.map((group) => <div key={group.id} role="group" aria-label={`${group.label} layers`} className="flex flex-col">
          <span className="px-2 text-micro text-muted-foreground/80">{group.label}</span>
          {group.layers.map((layer) => <FileSheetCheckboxRow key={layer.id} label={layer.label} checked={drawn.has(layer.id)}
            onCheckedChange={(shown) => onChange(toggleBoardLayer(display, sheet, layer.id, shown))} />)}
        </div>)}
      </div>
    </FileSheetSettingsSection> : null}
  </>;
}
