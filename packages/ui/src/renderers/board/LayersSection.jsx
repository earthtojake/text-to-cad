import { useI18n } from "@text-to-cad/ui/i18n";
const GROUP_KEYS = {"front": "board.text.front", "inner": "board.text.inner", "back": "board.text.back", "other": "board.text.other"};
const THROUGH_KEYS = {"vias": "board.text.vias", "ratsnest": "board.text.ratsnest", "drills": "board.text.drills"};
import { useMemo } from "react";
import { Eye, EyeOff, Layers } from "lucide-react";
import { boardDisplayLayers, boardLayerGroups, layerColor, toggleBoardLayer } from "@text-to-cad/core/lib/plot2d/index.js";
import { Button } from "@text-to-cad/ui/primitives/button";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { ROW_NAME_UNDER_ACTIONS, TreeRowLabel, TreeRowSurface, treeRowActionsClass } from "@text-to-cad/ui/primitives/tree-row";
import { cn } from "@text-to-cad/ui/utils";
import { LAYER_ROW_INSET_PX, LayerSwatch } from "../kit/inspector/layerRows.jsx";
import ToolPanel from "../kit/tools/ToolPanel.jsx";

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
 * every layer the board's picture holds, grouped as KiCad stacks them — Front (outermost first),
 * Inner, Back, then Other (the outline, the user layers, the vias, the ratsnest and the drill holes)
 * — each with its colour, its name, how many things it draws, and an eye that hides or shows it in
 * the view. A layer has nothing under it, so its one glyph is its colour (KiCad's, `plot2d/theme.js`),
 * on the section title's line with the groups' labels (`kit/inspector/layerRows.jsx`). A layer hidden or shown is the board's Display (`plot2d/boardDisplay.js`'s `layers`), the
 * one object `cadgen pcb snapshot --display` draws, so the view and a snapshot never disagree; a set
 * the mode does not draw reads as Custom in Display.
 *
 * @param {{ sheet: { layers: { id: string, kind: string, side: string, items: unknown[] }[] },
 *   display: ReturnType<typeof import("@text-to-cad/core/lib/plot2d/index.js").readBoardDisplay>,
 *   onDisplayChange(display: object): void }} props
 */
export default function LayersSection({ sheet, display, onDisplayChange }) {
  const { t } = useI18n();
  const groups = useMemo(() => boardLayerGroups(sheet).map(group => ({ ...group, label: t(GROUP_KEYS[group.id]) })), [sheet, t]);
  const counts = useMemo(() => new Map(sheet.layers.map(layer => [layer.id, layer.items.length])), [sheet, t]);
  const drawn = useMemo(() => new Set(boardDisplayLayers(display, sheet)), [display, sheet]);
  const toggle = (id, hidden) => onDisplayChange(toggleBoardLayer(display, sheet, id, hidden));
  return <ToolPanel id="layers" title={t("layers.title")} label={t("layers.title")} fit="tree" resizable collapsible={false} icon={Layers}>
    <div className="px-1 py-1 text-tiny" aria-label={t("board.text.board_layers")} data-board-layers="">
      {groups.map(group => <ul key={group.id} aria-label={t("board.text.name_layers", { name: group.label })} data-layer-group={group.id}>
        <li className="flex h-6 items-center text-muted-foreground" style={{ paddingLeft: LAYER_ROW_INSET_PX }} aria-hidden="true">{group.label}</li>
        {group.layers.map(layer => {
          const hidden = !drawn.has(layer.id);
          return <li key={layer.id} className="min-w-0">
            <TreeRowSurface dense className="group/row gap-0 pr-0" style={{ paddingLeft: LAYER_ROW_INSET_PX, "--row-actions": ROW_ACTIONS_WIDTH }} data-layer-row={layer.id}>
              <LayerSwatch color={layerColor(layer.id)} />
              <span className={cn("flex h-full min-w-0 flex-1 items-center gap-1.5 pl-1 pr-2", hidden && "text-muted-foreground",
                hidden ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover)}>
                <TreeRowLabel className="max-w-full shrink-0">{THROUGH_KEYS[layer.id] ? t(THROUGH_KEYS[layer.id]) : layer.label}</TreeRowLabel>
                <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{(counts.get(layer.id) ?? 0).toLocaleString("en-US")}</TreeRowLabel>
              </span>
              <LayerEye id={layer.id} hidden={hidden} onToggle={toggle} />
            </TreeRowSurface>
          </li>;
        })}
      </ul>)}
    </div>
  </ToolPanel>;
}
