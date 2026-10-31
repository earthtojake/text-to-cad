import { useMemo, useState } from "react";
import { Box, Eye, EyeOff } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import {
  ROW_NAME_UNDER_ACTIONS, TREE_GLYPH_STROKE, TREE_ROW_DENSE_ICON_CLASS, TreeRowChevron, TreeRowGuides, TreeRowLabel,
  TreeRowSurface, treeRowActionsClass
} from "@text-to-cad/ui/primitives/tree-row";
import { cn } from "@text-to-cad/ui/utils";
import ToolPanel from "../kit/tools/ToolPanel.jsx";
import { useControlUsage } from "../../usage/controls.js";
import { drawingReferenceId, layerRows } from "./drawingReferences.js";
import { useI18n } from "@text-to-cad/ui/i18n";

// The room the eye takes at a row's right end: the row's `--row-actions`.
const ROW_ACTIONS_WIDTH = "1.5rem";
// A block reference hangs under its layer with its glyph under the layer's swatch: past the chevron's column.
const INSERT_INDENT_PX = 16;

/** A layer's pen: a small swatch, the theme's foreground for the default pen. */
function Swatch({ color }) {
  return <span className="grid h-6 w-4 shrink-0 place-items-center" aria-hidden="true">
    <span className="block size-2.5 rounded-[3px] shadow-[inset_0_0_0_1px_color-mix(in_oklab,currentColor_35%,transparent)]"
      style={{ backgroundColor: color || "var(--foreground)" }} />
  </span>;
}

/** A layer's Hide/Reveal eye, as a tree row's is: over the row's right end, on hover, kept while hidden. */
function LayerEye({ name, hidden, onToggle }) {
  const usage = useControlUsage();
  const { t } = useI18n();
  const action = hidden ? t("tree.reveal") : t("tree.hide");
  return <div data-row-actions="" className={treeRowActionsClass(hidden)}>
    <TooltipHint content={action}>
      <Button type="button" variant="ghost" size="icon-xs" aria-label={t(hidden ? "layers.revealNamed" : "layers.hideNamed", { name })} aria-pressed={hidden} className="h-5 w-4 text-muted-foreground"
        data-layer-visibility={name} onClick={event => { event.stopPropagation(); usage.used("layer_visibility"); onToggle(name); }}>
        {hidden ? <EyeOff className="size-3" aria-hidden="true" /> : <Eye className="size-3" aria-hidden="true" />}
      </Button>
    </TooltipHint>
  </div>;
}

/**
 * A drawing's **Layers**, a section of the file sidebar for a drawing with the structure to read
 * (`layersSectionShown`): each layer drawn on, in the drawing's order — its pen, its name, how many
 * entities drew on it, and its eye, which hides or shows it in the view (a hidden layer is not drawn
 * and nothing on it is picked or snapped to) — and under a layer, the block references placed on
 * it, each a row of its block's name that selects it as a click on the drawing does (Shift adds).
 *
 * @param {{ drawing: import("@text-to-cad/core/lib/drawing2d/drawing.js").PreparedDrawing,
 *   hiddenLayers: ReadonlySet<string>, onToggleLayer(name: string): void,
 *   selection: ReturnType<typeof import("../kit/tools/select/useSceneSelection.js").useSceneSelection> }} props
 */
export default function LayersSection({ drawing, hiddenLayers, onToggleLayer, selection }) {
  const { t } = useI18n();
  const rows = useMemo(() => layerRows(drawing), [drawing]);
  // A layer with block references on it opens on them; the person folds it from there.
  const [folded, setFolded] = useState(() => new Set());
  const chosen = useMemo(() => new Set(selection.selected), [selection.selected]);
  const toggle = name => setFolded(current => {
    const next = new Set(current);
    if (!next.delete(name)) next.add(name);
    return next;
  });
  return <ToolPanel id="layers" title={t("layers.title")} label={t("layers.title")} fit="tree" resizable collapsible={false}>
    <ul className="px-1 py-1 text-tiny" aria-label={t("layers.label")} data-drawing-layers="">
      {rows.map(row => {
        const hidden = hiddenLayers.has(row.name), open = row.inserts.length > 0 && !folded.has(row.name);
        return <li key={row.name} className="min-w-0">
          <TreeRowSurface dense className="group/row gap-0 pr-0" style={{ "--row-actions": ROW_ACTIONS_WIDTH }} data-layer-row={row.name}>
            {row.inserts.length ? <button type="button" aria-label={t(open ? "tree.collapse" : "tree.expand", { name: row.name })} aria-expanded={open}
              className="grid h-6 w-4 shrink-0 place-items-center rounded focus-visible:ring-2 focus-visible:ring-ring" onClick={() => toggle(row.name)}>
              <TreeRowChevron expanded={open} />
            </button> : <span className="w-4 shrink-0" aria-hidden="true" />}
            <Swatch color={row.color} />
            <span className={cn("flex h-full min-w-0 flex-1 items-center gap-1.5 pl-1 pr-2", hidden && "text-muted-foreground",
              hidden ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover)}>
              <TreeRowLabel className="max-w-full shrink-0">{row.name}</TreeRowLabel>
              <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{row.entities.toLocaleString("en-US")}</TreeRowLabel>
            </span>
            <LayerEye name={row.name} hidden={hidden} onToggle={onToggleLayer} />
          </TreeRowSurface>
          {open ? <ul>{row.inserts.map(insert => {
            const id = drawingReferenceId(insert.handle);
            return <li key={insert.handle} className="min-w-0">
              <TreeRowSurface dense active={chosen.has(id)} className="gap-0" style={{ paddingLeft: INSERT_INDENT_PX }}
                onMouseEnter={() => selection.hover(id)} onMouseLeave={() => selection.hover("")}>
                <TreeRowGuides depth={1} column={16} />
                <span className="grid h-6 w-4 shrink-0 place-items-center" aria-hidden="true">
                  <Box className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} />
                </span>
                <button type="button" aria-label={t("layers.selectBlock", { name: insert.block || insert.handle })} aria-pressed={chosen.has(id)} data-insert-row={insert.handle}
                  onClick={event => selection.select(id, { multiSelect: event.shiftKey || event.metaKey || event.ctrlKey })}
                  className="flex h-full min-w-0 flex-1 items-center gap-1.5 rounded pl-1 pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <TreeRowLabel className="max-w-full shrink-0">{insert.block || t("layers.block")}</TreeRowLabel>
                  <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{insert.handle}</TreeRowLabel>
                </button>
              </TreeRowSurface>
            </li>;
          })}</ul> : null}
        </li>;
      })}
    </ul>
  </ToolPanel>;
}
