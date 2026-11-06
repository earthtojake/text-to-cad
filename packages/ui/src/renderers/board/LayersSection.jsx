import { useI18n } from "@cad/ui/i18n";
const GROUP_KEYS = {"front": "board.text.front", "inner": "board.text.inner", "back": "board.text.back", "other": "board.text.other"};
const THROUGH_KEYS = {"vias": "board.text.vias", "ratsnest": "board.text.ratsnest", "drills": "board.text.drills", "names": "board.text.names", "area": "board.text.board_area"};
import { useMemo } from "react";
import { Eye, EyeOff } from "lucide-react";
import {
  boardActiveLayer, boardDisplayLayers, boardLayerActivatable, boardLayerGroups, boardPalette, toggleBoardLayer
} from "@cad/core/lib/plot2d/index.js";
import { Button } from "@cad/ui/primitives/button";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { ROW_NAME_UNDER_ACTIONS, TreeRowLabel, TreeRowSurface, treeRowActionsClass } from "@cad/ui/primitives/tree-row";
import { cn } from "@cad/ui/utils";
import { LAYER_ROW_INSET_PX, LayerSwatch } from "../kit/inspector/layerRows.jsx";
import { useFlatPanel } from "../kit/shell/FlatPanel.jsx";
import { BoardLayerDisplaySettings } from "./BoardDisplay.jsx";

// The room the eye takes at a row's right end: the row's `--row-actions`.
const ROW_ACTIONS_WIDTH = "1.5rem";

/** A layer's Hide/Reveal eye, as a drawing's is: over the row's right end, on hover, kept while hidden. */
function LayerEye({ id, hidden, onToggle }) {
  const { t } = useI18n();
  const action = hidden ? t("tree.reveal") : t("tree.hide");
  // Its glyph ends on the panel's line, 16px in: the row's 8px, and 6px and the button's 2px inside it.
  return <div data-row-actions="" className={cn(treeRowActionsClass(hidden), "pr-1.5")}>
    <TooltipHint content={action}>
      <Button type="button" variant="ghost" size="icon-xs" aria-label={t(hidden ? "layers.revealNamed" : "layers.hideNamed", { name: id })} aria-pressed={hidden} className="h-5 w-4 text-muted-foreground"
        data-layer-visibility={id} onClick={event => { event.stopPropagation(); onToggle(id, hidden); }}>
        {hidden ? <EyeOff className="size-3" aria-hidden="true" /> : <Eye className="size-3" aria-hidden="true" />}
      </Button>
    </TooltipHint>
  </div>;
}

/**
 * A board's **Layers**, a tab of the view's panel (`kit/shell/FlatPanel.jsx`), as KiCad's Appearance
 * panel's Layers tab, a list as Altium's Layers panel is: every layer the
 * board's picture holds, grouped as KiCad lists them — Front (outermost first), Inner, Back, then
 * Other (the user layers and the outline, the board's area, the vias, the drill holes, the ratsnest
 * and the pads' and vias' names) — each with its colour, its name, how many things it draws, and an
 * eye that hides or shows it in the view; a press on a board layer's row makes it the **active**
 * layer, the one drawn on top and the one Others keeps bright (its filled dot after its name; until
 * one is pressed, KiCad's own, the copper facing the eye). A layer has nothing under it, so its one glyph is its
 * colour (KiCad's, in the view's theme: `plot2d/theme.js`, `kit/inspector/layerRows.jsx`). While the
 * panel's search is up, the layers whose names match, and nothing else. Everything here is the
 * board's Display (`plot2d/boardDisplay.js`), the one object `cad <type> snapshot --display` draws,
 * so the view and a snapshot never disagree; a set the preset does not draw reads as Custom. Under the
 * layers, **Layer display** (the other layers, the pours, the opacities), as
 * KiCad's Appearance panel has them (`BoardDisplay.jsx`): how the board is drawn, changed now and then, so
 * the panel's; the preset (Display) and the side, changed often, are the view's corner's.
 *
 * @param {{ sheet: { layers: { id: string, kind: string, side: string, items: unknown[] }[] },
 *   display: ReturnType<typeof import("@cad/core/lib/plot2d/index.js").readBoardDisplay>,
 *   onDisplayChange(display: object): void }} props
 */
export default function LayersSection({ sheet, display, onDisplayChange, colorScheme = "light" }) {
  const palette = boardPalette(colorScheme);
  const { t } = useI18n();
  const groups = useMemo(() => boardLayerGroups(sheet).map(group => ({ ...group, label: t(GROUP_KEYS[group.id]) })), [sheet, t]);
  const counts = useMemo(() => new Map(sheet.layers.map(layer => [layer.id, layer.items.length])), [sheet, t]);
  const drawn = useMemo(() => new Set(boardDisplayLayers(display, sheet)), [display, sheet]);
  const toggle = (id, hidden) => onDisplayChange(toggleBoardLayer(display, sheet, id, hidden));
  const active = boardActiveLayer(display, sheet);
  const change = patch => onDisplayChange({ ...display, ...patch });
  const query = useFlatPanel()?.query.trim().toLowerCase() ?? "";
  const nameOf = layer => (THROUGH_KEYS[layer.id] ? t(THROUGH_KEYS[layer.id]) : layer.label);
  const row = layer => {
    const hidden = !drawn.has(layer.id);
    const activatable = boardLayerActivatable(sheet, layer.id);
    const isActive = layer.id === active;
    const name = nameOf(layer);
    const label = <>
      <TreeRowLabel className="max-w-full shrink-0">{name}</TreeRowLabel>
      {isActive ? <span className="size-1.5 shrink-0 rounded-full bg-foreground" data-layer-active="" aria-hidden="true" /> : null}
      <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{(counts.get(layer.id) ?? 0).toLocaleString("en-US")}</TreeRowLabel>
    </>;
    const labelClass = cn("flex h-full min-w-0 flex-1 items-center gap-1.5 pl-1 pr-2 text-left", hidden && "text-muted-foreground",
      hidden ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover);
    return <li key={layer.id} className="min-w-0">
      <TreeRowSurface dense className="group/row gap-0 pr-0" style={{ paddingLeft: LAYER_ROW_INSET_PX, "--row-actions": ROW_ACTIONS_WIDTH }} data-layer-row={layer.id}>
        <LayerSwatch color={palette.layer(layer.id)} />
        {activatable ? <button type="button" className={cn(labelClass, "rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
          aria-label={t("board.text.make_active", { name })} aria-pressed={isActive} data-layer-activate={layer.id}
          onClick={() => change({ active: layer.id })}>{label}</button>
          : <span className={labelClass}>{label}</span>}
        <LayerEye id={layer.id} hidden={hidden} onToggle={toggle} />
      </TreeRowSurface>
    </li>;
  };
  // Searching: the layers whose names match, as one list; none, nothing (the panel leaves the tab out).
  if (query) {
    const found = groups.flatMap(group => group.layers).filter(layer => nameOf(layer).toLowerCase().includes(query) || layer.id.toLowerCase().includes(query));
    return found.length ? <ul className="px-2 text-tiny" aria-label={t("board.text.board_layers")} data-board-layers="" data-flat-panel-hit="">{found.map(row)}</ul> : null;
  }
  return <div className="flex flex-col pt-1 text-tiny">
    <div className="px-2" aria-label={t("board.text.board_layers")} data-board-layers="">
      {groups.map(group => <ul key={group.id} aria-label={t("board.text.name_layers", { name: group.label })} data-layer-group={group.id}>
        <li className="flex h-6 items-center text-muted-foreground" style={{ paddingLeft: LAYER_ROW_INSET_PX }} aria-hidden="true">{group.label}</li>
        {group.layers.map(row)}
      </ul>)}
    </div>
    <div className="mt-2 border-t border-border px-2 pt-1" data-board-display-settings="layer-display">
      <BoardLayerDisplaySettings display={display} sheet={sheet} onChange={onDisplayChange} />
    </div>
  </div>;
}
