import { useCallback, useMemo, useState } from "react";
import { Box, Eye, EyeOff, Layers } from "lucide-react";
import { Button } from "@cad/ui/primitives/button";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import {
  ROW_NAME_UNDER_ACTIONS, TREE_GLYPH_STROKE, TREE_ROW_DENSE_ICON_CLASS, TREE_ROW_NAME_CLASS, TreeRowActions, TreeRowGlyph, TreeRowLabel,
  TreeRowSurface, TreeRowToggle, useTreeRowHeight
} from "@cad/ui/primitives/tree-row";
import { cn } from "@cad/ui/utils";
import { useFlatPanel } from "../kit/shell/FlatPanel.jsx";
import { LayerSwatch } from "../kit/inspector/layerRows.jsx";
import VirtualRows from "../kit/inspector/VirtualRows.jsx";
import { useControlUsage } from "../../usage/controls.js";
import { drawingReferenceId, layerRows } from "./drawingReferences.js";
import { useI18n } from "@cad/ui/i18n";

/** A layer's Hide/Reveal eye, as a tree row's is: over the row's right end, on hover, kept while hidden. */
function LayerEye({ name, hidden, onToggle }) {
  const usage = useControlUsage();
  const { t } = useI18n();
  const action = hidden ? t("tree.reveal") : t("tree.hide");
  return <TreeRowActions persistent={hidden}>
    <TooltipHint content={action}>
      <Button type="button" variant="ghost" size="icon-xs" aria-label={t(hidden ? "layers.revealNamed" : "layers.hideNamed", { name })} aria-pressed={hidden} className="h-5 w-4 text-muted-foreground"
        data-layer-visibility={name} onClick={event => { event.stopPropagation(); usage.used("layer_visibility"); onToggle(name); }}>
        {hidden ? <EyeOff className="size-3" aria-hidden="true" /> : <Eye className="size-3" aria-hidden="true" />}
      </Button>
    </TooltipHint>
  </TreeRowActions>;
}

/** The layers a search keeps: a layer whose name matches, with all its block references, or one with a block that does (by
 * its block's name or its handle, `9C` or `#9C`), with those. */
function searchRows(rows, query) {
  if (!query) return rows;
  const has = text => String(text || "").toLowerCase().includes(query);
  return rows.flatMap(row => {
    if (has(row.name)) return [row];
    const inserts = row.inserts.filter(insert => has(insert.block) || has(`#${insert.handle}`));
    return inserts.length ? [{ ...row, inserts }] : [];
  });
}

/**
 * A drawing's **Layers**, the tab of the view's panel (`kit/shell/FlatPanel.jsx`) for a drawing with
 * the structure to read (`layersSectionShown`): each layer drawn on, in the drawing's order — its
 * pen, its name, how many entities drew on it, and its eye, which hides or shows it in the view (a
 * hidden layer is not drawn and nothing on it is picked or snapped to) — and under a layer, the
 * block references placed on it, each a row of its block's name that selects it as a click on the
 * drawing does (Shift adds). Every layer row is two glyphs, so none starts with a gap: its slot, 16px
 * in, holds its chevron where blocks hang under it, else a layer's icon, and the box after it its
 * colour. A block reference's row stands in line with its layer's: its slot only the layer's guide
 * (under the chevron), its box its block's glyph (under the colour), its name under the layer's name.
 * While the panel's search is up, the layers whose names match and the blocks whose names do, opened.
 * The rows are one flat list mounted as they scroll into view (`VirtualRows`), as a circuit's tree is:
 * a drawing of thousands of block references draws, and searches, only the rows on screen.
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
  // A layer with block references on it opens on them; the person folds it from there (a search opens them all).
  const [folded, setFolded] = useState(() => new Set());
  const chosen = useMemo(() => new Set(selection.selected), [selection.selected]);
  const toggle = name => setFolded(current => {
    const next = new Set(current);
    if (!next.delete(name)) next.add(name);
    return next;
  });
  // Each layer's row, then (opened) its block references', one flat list.
  const flat = useMemo(() => rows.flatMap(row => {
    const open = row.inserts.length > 0 && (Boolean(query) || !folded.has(row.name));
    return [{ row, open }, ...(open ? row.inserts.map(insert => ({ row, insert })) : [])];
  }), [rows, query, folded]);
  const rowHeight = useTreeRowHeight();
  const renderRow = useCallback(at => {
    const { row, open, insert } = flat[at];
    if (!insert) {
      const hidden = hiddenLayers.has(row.name);
      return <TreeRowSurface dense depth={0} actions={1} className="group/row" data-layer-row={row.name}>
        {row.inserts.length ? <TreeRowToggle open={open} label={t(open ? "tree.collapse" : "tree.expand", { name: row.name })} onToggle={() => toggle(row.name)} />
          : <TreeRowGlyph><Layers className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} /></TreeRowGlyph>}
        <LayerSwatch color={row.color} />
        <span className={cn(TREE_ROW_NAME_CLASS, hidden && "text-muted-foreground", hidden ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover)}>
          <TreeRowLabel className="max-w-full shrink-0">{row.name}</TreeRowLabel>
          <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{row.entities.toLocaleString("en-US")}</TreeRowLabel>
        </span>
        <LayerEye name={row.name} hidden={hidden} onToggle={onToggleLayer} />
      </TreeRowSurface>;
    }
    const id = drawingReferenceId(insert.handle);
    return <TreeRowSurface dense depth={0} active={chosen.has(id)}
      onMouseEnter={() => selection.hover(id)} onMouseLeave={() => selection.hover("")}>
      <TreeRowGlyph guide />
      <TreeRowGlyph><Box className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} /></TreeRowGlyph>
      {/* Its detail is its handle, the entity's id in the file (what its reference names, `#h9C`),
          marked as one and said whole in its tooltip: the payload carries no insertion point. */}
      <TooltipHint content={t("layers.handle", { handle: insert.handle })} side="right">
        <button type="button" aria-label={t("layers.selectBlock", { name: insert.block || insert.handle })} aria-pressed={chosen.has(id)} data-insert-row={insert.handle}
          onClick={event => selection.select(id, { multiSelect: event.shiftKey || event.metaKey || event.ctrlKey })}
          className={TREE_ROW_NAME_CLASS}>
          <TreeRowLabel className="max-w-full shrink-0">{insert.block || t("layers.block")}</TreeRowLabel>
          <TreeRowLabel className="flex-1 text-micro text-muted-foreground">#{insert.handle}</TreeRowLabel>
        </button>
      </TooltipHint>
    </TreeRowSurface>;
  }, [flat, hiddenLayers, chosen, selection, onToggleLayer, t]);
  if (query && !rows.length) return null;
  return <VirtualRows className="text-tiny" aria-label={t("layers.label")} data-drawing-layers="" data-flat-panel-hit={query ? "" : undefined}
    count={flat.length} rowHeight={rowHeight} rowKey={at => (flat[at].insert ? `insert:${flat[at].insert.handle}` : `layer:${flat[at].row.name}`)}
    rowProps={() => ({ className: "min-w-0" })} renderRow={renderRow} />;
}
