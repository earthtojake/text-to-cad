import { useI18n } from "@cad/ui/i18n";
const GROUP_KEYS = {"front": "board.text.front", "inner": "board.text.inner", "back": "board.text.back", "other": "board.text.other"};
const THROUGH_KEYS = {"vias": "board.text.vias", "ratsnest": "board.text.ratsnest", "drills": "board.text.drills", "names": "board.text.names", "area": "board.text.board_area"};
import { useMemo } from "react";
import { Box, Eye, EyeOff } from "lucide-react";
import {
  boardActiveLayer, boardDisplayLayers, boardLayerActivatable, boardLayerGroups, boardPalette, toggleBoardLayer
} from "@cad/core/lib/plot2d/index.js";
import { Button } from "@cad/ui/primitives/button";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import {
  ROW_NAME_UNDER_ACTIONS, TREE_GLYPH_STROKE, TREE_ROW_DENSE_ICON_CLASS, TREE_ROW_NAME_CLASS, TreeRowActions, TreeRowDetail, TreeRowGlyph, TreeRowHeading,
  TreeRowName, TreeRowSurface
} from "@cad/ui/primitives/tree-row";
import { TreeFilterMatch } from "@cad/ui/primitives/tree-filter";
import { cn } from "@cad/ui/utils";
import { LayerSwatch } from "../kit/inspector/layerRows.jsx";
import { useFlatPanel, useFlatPanelMatches } from "../kit/shell/FlatPanel.jsx";
import { BoardLayerDisplaySettings } from "./BoardDisplay.jsx";

/** A layer's Hide/Reveal eye, as a drawing's is: over the row's right end, on hover, kept while hidden. */
function LayerEye({ id, hidden, onToggle, label = null }) {
  const { t } = useI18n();
  const action = hidden ? t("tree.reveal") : t("tree.hide");
  return <TreeRowActions persistent={hidden}>
    <TooltipHint content={action}>
      <Button type="button" variant="ghost" size="icon-xs" aria-label={label || t(hidden ? "layers.revealNamed" : "layers.hideNamed", { name: id })} aria-pressed={hidden} className="cad-hit h-[calc(var(--cad-glyph)+4px)] w-glyph text-muted-foreground"
        data-layer-visibility={id} onClick={event => { event.stopPropagation(); onToggle(id, hidden); }}>
        {hidden ? <EyeOff className="size-3" aria-hidden="true" /> : <Eye className="size-3" aria-hidden="true" />}
      </Button>
    </TooltipHint>
  </TreeRowActions>;
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
 * the panel's; the preset (Style) and the side (Side), changed often, are the Display card's. Last in Other,
 * **3D models**: the parts' models in the 3D view (how many parts stand on one, and an eye), a seldom-used
 * control kept here in both modes so the panel never differs between them; in 2D it changes nothing drawn.
 *
 * @param {{ sheet: { layers: { id: string, kind: string, side: string, items: unknown[] }[] },
 *   display: ReturnType<typeof import("@cad/core/lib/plot2d/index.js").readBoardDisplay>,
 *   onDisplayChange(display: object): void }} props
 */
export default function LayersSection({ sheet, display, onDisplayChange, colorScheme = "light", models = null }) {
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
      <TreeRowName><TreeFilterMatch text={name} query={query} /></TreeRowName>
      {isActive ? <span className="size-1.5 shrink-0 rounded-full bg-foreground" data-layer-active="" aria-hidden="true" /> : null}
      <TreeRowDetail>{(counts.get(layer.id) ?? 0).toLocaleString("en-US")}</TreeRowDetail>
    </>;
    const labelClass = cn(TREE_ROW_NAME_CLASS, hidden && "text-muted-foreground", hidden ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover);
    return <li key={layer.id} className="min-w-0">
      <TreeRowSurface dense depth={0} actions={1} className="group/row" data-layer-row={layer.id}>
        <LayerSwatch color={palette.layer(layer.id)} />
        {activatable ? <button type="button" className={labelClass}
          aria-label={t("board.text.make_active", { name })} aria-pressed={isActive} data-layer-activate={layer.id}
          onClick={() => change({ active: layer.id })}>{label}</button>
          : <span className={labelClass}>{label}</span>}
        <LayerEye id={layer.id} hidden={hidden} onToggle={toggle} />
      </TreeRowSurface>
    </li>;
  };
  // The parts' 3D models, a row of Other: its glyph a box, its count the parts with a model, its eye the 3D view's.
  const modelsRow = models ? <li key="models-3d" className="min-w-0">
    <TreeRowSurface dense depth={0} actions={1} className="group/row" data-layer-row="models-3d">
      <TreeRowGlyph><Box className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} /></TreeRowGlyph>
      <span className={cn(TREE_ROW_NAME_CLASS, !models.shown && "text-muted-foreground", models.shown ? ROW_NAME_UNDER_ACTIONS.hover : ROW_NAME_UNDER_ACTIONS.shown)}>
        <TreeRowName><TreeFilterMatch text={t("board.text.models_3d")} query={query} /></TreeRowName>
        <TreeRowDetail>{models.count.toLocaleString("en-US")}</TreeRowDetail>
      </span>
      <LayerEye id="models-3d" hidden={!models.shown} onToggle={() => models.onChange(!models.shown)}
        label={t(models.shown ? "board.text.hide_models" : "board.text.show_models")} />
    </TreeRowSurface>
  </li> : null;
  const modelsMatch = Boolean(models) && t("board.text.models_3d").toLowerCase().includes(query);
  const found = query ? groups.flatMap(group => group.layers).filter(layer => nameOf(layer).toLowerCase().includes(query) || layer.id.toLowerCase().includes(query)) : null;
  useFlatPanelMatches(found ? found.length + (modelsMatch ? 1 : 0) : null);
  // Searching: the layers whose names match, as one list; none, nothing (the panel leaves the tab out).
  if (found) {
    return found.length || modelsMatch ? <ul aria-label={t("board.text.board_layers")} data-board-layers="" data-flat-panel-hit="">
      {found.map(row)}{modelsMatch ? modelsRow : null}</ul> : null;
  }
  return <div className="flex flex-col">
    <div aria-label={t("board.text.board_layers")} data-board-layers="">
      {groups.map(group => <ul key={group.id} aria-label={t("board.text.name_layers", { name: group.label })} data-layer-group={group.id}>
        <TreeRowHeading as="li" aria-hidden="true">{group.label}</TreeRowHeading>
        {group.layers.map(row)}
        {group.id === "other" ? modelsRow : null}
      </ul>)}
      {modelsRow && !groups.some(group => group.id === "other") ? <ul data-layer-group="other">{modelsRow}</ul> : null}
    </div>
    {/* ONE hairline, as the Joints tab and the Display card draw theirs (the rows' line, 12px of air over and under it),
        then the settings on the panel's lines. */}
    <div className="mt-3 border-t border-border pt-3" data-board-layer-rule="" />
    <div data-board-display-settings="layer-display">
      <BoardLayerDisplaySettings display={display} sheet={sheet} onChange={onDisplayChange} />
    </div>
  </div>;
}
