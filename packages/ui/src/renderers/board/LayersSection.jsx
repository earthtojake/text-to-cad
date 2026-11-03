import { useI18n } from "@cad/ui/i18n";
const GROUP_KEYS = {"front": "board.text.front", "inner": "board.text.inner", "back": "board.text.back", "other": "board.text.other"};
const THROUGH_KEYS = {"vias": "board.text.vias", "ratsnest": "board.text.ratsnest", "drills": "board.text.drills", "names": "board.text.names", "area": "board.text.board_area"};
import { useMemo } from "react";
import { Eye, EyeOff, Layers } from "lucide-react";
import {
  BOARD_DISPLAY_DEFAULTS, boardActiveLayer, boardDisplayLayers, boardLayerActivatable, boardLayerGroups, layerColor, toggleBoardLayer
} from "@cad/core/lib/plot2d/index.js";
import { Button } from "@cad/ui/primitives/button";
import { Checkbox } from "@cad/ui/primitives/checkbox";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { ROW_NAME_UNDER_ACTIONS, TreeRowLabel, TreeRowSurface, treeRowActionsClass } from "@cad/ui/primitives/tree-row";
import { cn } from "@cad/ui/utils";
import { LAYER_ROW_INSET_PX, LayerSwatch } from "../kit/inspector/layerRows.jsx";
import ToolPanel from "../kit/tools/ToolPanel.jsx";
import { Slider } from "@cad/ui/primitives/slider";
import { FILE_SHEET_SECTION_HEADING_CLASSES, FileSheetSliderField, parseFileSheetNumberInput } from "../kit/inspector/FileSheet.js";

const percent = value => `${Math.round(value * 100)}%`;
/**
 * An opacity's row, as a settings form's slider field is (`FileSheetSliderField`): its short label
 * over its slider, its committed percentage beside them, so it fits the sidebar's width.
 */
function OpacityField({ label, name, value, onChange }) {
  const { t } = useI18n();
  return <FileSheetSliderField label={label} labelTitle={name} value={percent(value)}
    onValueCommit={draft => { const next = parseFileSheetNumberInput(draft, { fallback: value * 100, min: 0, max: 100 }) / 100; if (next !== value) onChange(next); }}
    valueInputProps={{ ariaLabel: t("render.valueOf", { name }) }}>
    <Slider className="h-4 min-w-0" value={[value]} min={0} max={1} step={0.01} thumbProps={{ "aria-label": name }}
      onValueChange={([next]) => onChange(next)} />
  </FileSheetSliderField>;
}
// The room the eye takes at a row's right end: the row's `--row-actions`.
const ROW_ACTIONS_WIDTH = "1.5rem";

/** A layer's Hide/Reveal eye, as a drawing's is: over the row's right end, on hover, kept while hidden. */
function LayerEye({ id, hidden, onToggle }) {
  const { t } = useI18n();
  const action = hidden ? t("tree.reveal") : t("tree.hide");
  return <div data-row-actions="" className={treeRowActionsClass(hidden)}>
    <TooltipHint content={action}>
      <Button type="button" variant="ghost" size="icon-xs" aria-label={t(hidden ? "layers.revealNamed" : "layers.hideNamed", { name: id })} aria-pressed={hidden} className="h-5 w-4 text-muted-foreground"
        data-layer-visibility={id} onClick={event => { event.stopPropagation(); onToggle(id, hidden); }}>
        {hidden ? <EyeOff className="size-3" aria-hidden="true" /> : <Eye className="size-3" aria-hidden="true" />}
      </Button>
    </TooltipHint>
  </div>;
}

/**
 * A board's **Layers**, a section of the file sidebar, as a drawing's is (`../dxf/LayersSection.jsx`):
 * headed by how the layers are drawn, as KiCad's Appearance panel's Layer Display Options are —
 * **Dim other layers** (a checkbox at its row's right end, as every switch in a settings form is:
 * KiCad's "Inactive layers: Dim", every layer but the active one drawn faded), then the **Zones**'
 * fill opacity (KiCad's 60%) and the **Tracks**' (100%), each a slider and its committed value —
 * then every layer the board's picture holds, grouped as KiCad lists them — Front (outermost first),
 * Inner, Back, then Other (the user layers and the outline, the board's area, the
 * vias, the drill holes, the ratsnest and the pads' and vias' names)
 * — each with its colour, its name, how many things it draws, and an eye that hides or shows it in
 * the view; a press on a board layer's row makes it the **active** layer, the one drawn on top (its
 * filled dot after its name; until one is pressed, KiCad's own, the copper facing the eye). A
 * layer has nothing under it, so its one glyph is its colour (KiCad's, `plot2d/theme.js`),
 * on the section title's line with the groups' labels (`kit/inspector/layerRows.jsx`). A layer hidden or shown, the active one, Dim
 * and the opacities are the board's Display (`plot2d/boardDisplay.js`'s `layers`, `active`, `dim`, `zones`, `tracks`), the
 * one object `cad <type> snapshot --display` draws, so the view and a snapshot never disagree; a set
 * the mode does not draw reads as Custom in Display.
 *
 * @param {{ sheet: { layers: { id: string, kind: string, side: string, items: unknown[] }[] },
 *   display: ReturnType<typeof import("@cad/core/lib/plot2d/index.js").readBoardDisplay>,
 *   onDisplayChange(display: object): void }} props
 */
export default function LayersSection({ sheet, display, onDisplayChange }) {
  const { t } = useI18n();
  const groups = useMemo(() => boardLayerGroups(sheet).map(group => ({ ...group, label: t(GROUP_KEYS[group.id]) })), [sheet, t]);
  const counts = useMemo(() => new Map(sheet.layers.map(layer => [layer.id, layer.items.length])), [sheet, t]);
  const drawn = useMemo(() => new Set(boardDisplayLayers(display, sheet)), [display, sheet]);
  const toggle = (id, hidden) => onDisplayChange(toggleBoardLayer(display, sheet, id, hidden));
  const active = boardActiveLayer(display, sheet);
  const change = patch => onDisplayChange({ ...display, ...patch });
  return <ToolPanel id="layers" title={t("layers.title")} label={t("layers.title")} fit="tree" resizable collapsible={false} icon={Layers}>
    <div className="border-b border-border px-1 pb-1" data-board-layer-options="">
      <label className={cn(FILE_SHEET_SECTION_HEADING_CLASSES, "cursor-pointer justify-between")}>
        <span className="truncate">{t("board.text.dim_other_layers")}</span>
        <Checkbox aria-label={t("board.text.dim_other_layers")} checked={display.dim === true} data-board-dim=""
          onCheckedChange={checked => change({ dim: checked === true })} />
      </label>
      <div className="px-1">
        <OpacityField label={t("board.text.zones")} name={t("board.text.zone_opacity")} value={display.zones ?? BOARD_DISPLAY_DEFAULTS.zones}
          onChange={zones => change({ zones })} />
        <OpacityField label={t("board.text.tracks")} name={t("board.text.track_opacity")} value={display.tracks ?? BOARD_DISPLAY_DEFAULTS.tracks}
          onChange={tracks => change({ tracks })} />
      </div>
    </div>
    <div className="px-1 py-1 text-tiny" aria-label={t("board.text.board_layers")} data-board-layers="">
      {groups.map(group => <ul key={group.id} aria-label={t("board.text.name_layers", { name: group.label })} data-layer-group={group.id}>
        <li className="flex h-6 items-center text-muted-foreground" style={{ paddingLeft: LAYER_ROW_INSET_PX }} aria-hidden="true">{group.label}</li>
        {group.layers.map(layer => {
          const hidden = !drawn.has(layer.id);
          const activatable = boardLayerActivatable(sheet, layer.id);
          const isActive = layer.id === active;
          const name = THROUGH_KEYS[layer.id] ? t(THROUGH_KEYS[layer.id]) : layer.label;
          const label = <>
            <TreeRowLabel className="max-w-full shrink-0">{name}</TreeRowLabel>
            {isActive ? <span className="size-1.5 shrink-0 rounded-full bg-foreground" data-layer-active="" aria-hidden="true" /> : null}
            <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{(counts.get(layer.id) ?? 0).toLocaleString("en-US")}</TreeRowLabel>
          </>;
          const labelClass = cn("flex h-full min-w-0 flex-1 items-center gap-1.5 pl-1 pr-2 text-left", hidden && "text-muted-foreground",
            hidden ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover);
          return <li key={layer.id} className="min-w-0">
            <TreeRowSurface dense className="group/row gap-0 pr-0" style={{ paddingLeft: LAYER_ROW_INSET_PX, "--row-actions": ROW_ACTIONS_WIDTH }} data-layer-row={layer.id}>
              <LayerSwatch color={layerColor(layer.id)} />
              {activatable ? <button type="button" className={cn(labelClass, "rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
                aria-label={t("board.text.make_active", { name })} aria-pressed={isActive} data-layer-activate={layer.id}
                onClick={() => change({ active: layer.id })}>{label}</button>
                : <span className={labelClass}>{label}</span>}
              <LayerEye id={layer.id} hidden={hidden} onToggle={toggle} />
            </TreeRowSurface>
          </li>;
        })}
      </ul>)}
    </div>
  </ToolPanel>;
}
