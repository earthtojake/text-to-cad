import { useMemo, useState } from "react";
import { Box, Eye, EyeOff } from "lucide-react";
import { Button } from "@cad/ui/primitives/button";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import {
  ROW_NAME_UNDER_ACTIONS, TREE_GLYPH_STROKE, TREE_ROW_DENSE_ICON_CLASS, TreeRowChevron, TreeRowLabel,
  TreeRowSurface, treeRowActionsClass
} from "@cad/ui/primitives/tree-row";
import { cn } from "@cad/ui/utils";
import { useFlatPanel } from "../kit/shell/FlatPanel.jsx";
import { LAYER_ROW_INSET_PX, LayerSwatch } from "../kit/inspector/layerRows.jsx";
import { useControlUsage } from "../../usage/controls.js";
import { drawingReferenceId, layerRows } from "./drawingReferences.js";
import { useI18n } from "@cad/ui/i18n";

// The room the eye takes at a row's right end: the row's `--row-actions`.
const ROW_ACTIONS_WIDTH = "1.5rem";
// A row's glyphs and name, 6px apart.
const GLYPH_GAP = "gap-1.5";
// The chevrons' column: a chevron's width, whatever size the chevron is drawn (a phone's is 16px).
const CHEVRON_COLUMN_CLASS = "grid h-6 min-w-3 shrink-0 place-items-center";
/**
 * The chevrons' column with no chevron in it, so a block reference's glyph stands under its layer's
 * colour; under an open layer, its guide down the middle of the column, under the chevron.
 */
const NoChevron = ({ guide = false }) => <span className={cn(CHEVRON_COLUMN_CLASS, "relative h-auto self-stretch")} aria-hidden="true">
  <span className="invisible"><TreeRowChevron expanded={false} /></span>
  {guide ? <span className="pointer-events-none absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-border" data-tree-guide="" /> : null}
</span>;

/** A layer's Hide/Reveal eye, as a tree row's is: over the row's right end, on hover, kept while hidden. */
function LayerEye({ name, hidden, onToggle }) {
  const usage = useControlUsage();
  const { t } = useI18n();
  const action = hidden ? t("tree.reveal") : t("tree.hide");
  // Its glyph ends on the panel's line, 16px in: the row's 8px, and 6px and the button's 2px inside it.
  return <div data-row-actions="" className={cn(treeRowActionsClass(hidden), "pr-1.5")}>
    <TooltipHint content={action}>
      <Button type="button" variant="ghost" size="icon-xs" aria-label={t(hidden ? "layers.revealNamed" : "layers.hideNamed", { name })} aria-pressed={hidden} className="h-5 w-4 text-muted-foreground"
        data-layer-visibility={name} onClick={event => { event.stopPropagation(); usage.used("layer_visibility"); onToggle(name); }}>
        {hidden ? <EyeOff className="size-3" aria-hidden="true" /> : <Eye className="size-3" aria-hidden="true" />}
      </Button>
    </TooltipHint>
  </div>;
}

/** The layers a search keeps: a layer whose name matches, with all its block references, or one with a block that does, with those. */
function searchRows(rows, query) {
  if (!query) return rows;
  const has = text => String(text || "").toLowerCase().includes(query);
  return rows.flatMap(row => {
    if (has(row.name)) return [row];
    const inserts = row.inserts.filter(insert => has(insert.block) || has(insert.handle));
    return inserts.length ? [{ ...row, inserts }] : [];
  });
}

/**
 * A drawing's **Layers**, the tab of the view's panel (`kit/shell/FlatPanel.jsx`) for a drawing with
 * the structure to read (`layersSectionShown`): each layer drawn on, in the drawing's order — its
 * pen, its name, how many entities drew on it, and its eye, which hides or shows it in the view (a
 * hidden layer is not drawn and nothing on it is picked or snapped to) — and under a layer, the
 * block references placed on it, each a row of its block's name that selects it as a click on the
 * drawing does (Shift adds). The rows stand on the panel's lines (`kit/inspector/layerRows.jsx`):
 * the first glyph — a layer's chevron where blocks hang under it, else its colour — 16px in. While
 * the panel's search is up, the layers whose names match and the blocks whose names do, opened.
 *
 * @param {{ drawing: import("@cad/core/lib/drawing2d/drawing.js").PreparedDrawing,
 *   hiddenLayers: ReadonlySet<string>, onToggleLayer(name: string): void,
 *   selection: ReturnType<typeof import("../kit/tools/select/useSceneSelection.js").useSceneSelection> }} props
 */
export default function LayersSection({ drawing, hiddenLayers, onToggleLayer, selection }) {
  const { t } = useI18n();
  const all = useMemo(() => layerRows(drawing), [drawing]);
  const query = useFlatPanel()?.query.trim().toLowerCase() ?? "";
  const rows = useMemo(() => searchRows(all, query), [all, query]);
  // The chevrons' column, only where some layer has blocks under it: else the colours start the rows.
  const branched = all.some(row => row.inserts.length > 0);
  // A layer with block references on it opens on them; the person folds it from there (a search opens them all).
  const [folded, setFolded] = useState(() => new Set());
  const chosen = useMemo(() => new Set(selection.selected), [selection.selected]);
  const toggle = name => setFolded(current => {
    const next = new Set(current);
    if (!next.delete(name)) next.add(name);
    return next;
  });
  if (query && !rows.length) return null;
  return <ul className="px-2 text-tiny" aria-label={t("layers.label")} data-drawing-layers="" data-flat-panel-hit={query ? "" : undefined}>
    {rows.map(row => {
      const hidden = hiddenLayers.has(row.name), open = row.inserts.length > 0 && (Boolean(query) || !folded.has(row.name));
      return <li key={row.name} className="min-w-0">
        <TreeRowSurface dense className={cn("group/row pr-0", GLYPH_GAP)} style={{ paddingLeft: LAYER_ROW_INSET_PX, "--row-actions": ROW_ACTIONS_WIDTH }} data-layer-row={row.name}>
          {row.inserts.length ? <button type="button" aria-label={t(open ? "tree.collapse" : "tree.expand", { name: row.name })} aria-expanded={open}
            className={cn(CHEVRON_COLUMN_CLASS, "rounded focus-visible:ring-2 focus-visible:ring-ring")} onClick={() => toggle(row.name)}>
            <TreeRowChevron expanded={open} />
          </button> : branched ? <NoChevron /> : null}
          <LayerSwatch color={row.color} />
          <span className={cn("flex h-full min-w-0 flex-1 items-center gap-1.5 pr-2", hidden && "text-muted-foreground",
            hidden ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover)}>
            <TreeRowLabel className="max-w-full shrink-0">{row.name}</TreeRowLabel>
            <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{row.entities.toLocaleString("en-US")}</TreeRowLabel>
          </span>
          <LayerEye name={row.name} hidden={hidden} onToggle={onToggleLayer} />
        </TreeRowSurface>
        {open ? <ul>{row.inserts.map(insert => {
          const id = drawingReferenceId(insert.handle);
          return <li key={insert.handle} className="min-w-0">
            <TreeRowSurface dense active={chosen.has(id)} className={GLYPH_GAP} style={{ paddingLeft: LAYER_ROW_INSET_PX }}
              onMouseEnter={() => selection.hover(id)} onMouseLeave={() => selection.hover("")}>
              <NoChevron guide />
              {/* At least the glyph column's 12px: a phone's 16px glyph widens it rather than overrunning the name. */}
              <span className="flex h-6 min-w-3 shrink-0 items-center" aria-hidden="true">
                <Box className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} />
              </span>
              <button type="button" aria-label={t("layers.selectBlock", { name: insert.block || insert.handle })} aria-pressed={chosen.has(id)} data-insert-row={insert.handle}
                onClick={event => selection.select(id, { multiSelect: event.shiftKey || event.metaKey || event.ctrlKey })}
                className="flex h-full min-w-0 flex-1 items-center gap-1.5 rounded pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                <TreeRowLabel className="max-w-full shrink-0">{insert.block || t("layers.block")}</TreeRowLabel>
                <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{insert.handle}</TreeRowLabel>
              </button>
            </TreeRowSurface>
          </li>;
        })}</ul> : null}
      </li>;
    })}
  </ul>;
}
