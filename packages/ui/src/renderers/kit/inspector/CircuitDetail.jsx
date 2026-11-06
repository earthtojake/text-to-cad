import { memo, useCallback, useMemo, useRef } from "react";
import { TREE_GLYPH_STROKE, TREE_ROW_DENSE_ICON_CLASS, TREE_ROW_NAME_CLASS, TreeRowGlyph, TreeRowLabel, TreeRowSurface, useTreeRowHeight } from "@cad/ui/primitives/tree-row";
import { cn } from "@cad/ui/utils";
import { useFlatPanel } from "../shell/FlatPanel.jsx";
import VirtualRows from "./VirtualRows.jsx";
import { InfoRow, MonoValue } from "./referenceRows.jsx";

const additive = event => event.shiftKey || event.metaKey || event.ctrlKey;

function Glyph({ kind, glyphs }) {
  const Icon = glyphs[kind] || glyphs.pad;
  return <TreeRowGlyph><Icon className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} /></TreeRowGlyph>;
}

// One pad or pin: its glyph, its name (a number under its part, a part and a number under a net), and its muted detail.
function DetailRow({ node, lit, choose, frame, hover, glyphs, data }) {
  return <TreeRowSurface dense depth={0} active={lit} className="group/row" onMouseEnter={() => hover(node.pick)} onMouseLeave={() => hover("")}>
    <Glyph kind={node.kind} glyphs={glyphs} />
    <button type="button" aria-pressed={lit} onClick={event => choose(node, event)} onDoubleClick={() => frame(node)} {...{ [`data-${data}-detail-row`]: node.id }}
      className={TREE_ROW_NAME_CLASS}>
      <TreeRowLabel className="max-w-full shrink-0">{node.label}</TreeRowLabel>
      {node.detail ? <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{node.detail}</TreeRowLabel> : null}
    </button>
  </TreeRowSurface>;
}
const MemoDetailRow = memo(DetailRow);

/**
 * What is selected, under a flat view's lists (`FlatPanel.jsx`'s `detail`), as a CAD tool's Properties
 * panel answers it: first **what it is** — its glyph, its name (`U3.5`, `VBUS · track`), a line saying what
 * that is in words ("Pad of U3 · ATmega328P"), and its facts (its net, layer, size, position: the
 * renderer's, the same a Quick Edit chip's card holds) — then **what it is connected to**: the other pads or
 * pins on its net (a part's own pads or pins, each with its net), titled with whose they are. Several
 * things selected say how many, and list them. Nothing with a net or pads of its own (a text, a graphic,
 * an area) has its facts alone.
 *
 * A row selects its pad or pin as a press on the picture does (Shift, Ctrl or Cmd adds or takes away),
 * lit while it is selected, and a double-click frames it, as the lists' rows do; the pointer on a row
 * lights it on the picture. The head's name selects what it is the detail of again, and a double-click
 * frames it. Its rows are mounted as they scroll into view.
 *
 * @param {{ detail: { id: string, kind: string, pick: string, label: string, detail: string, count: string, listLabel: string,
 *   facts?: { label: string, value: string }[], rows: { id: string, kind: string, pick: string, label: string, detail: string }[] },
 *   selection: ReturnType<typeof import("../tools/select/useSceneSelection.js").useSceneSelection>,
 *   glyphs: Record<string, import("react").ComponentType<any>>, data: string, onSelect(): void,
 *   onShow?(ids: readonly string[]): void, onFrame?(ids: readonly string[]): void }} props
 */
export default function CircuitDetail({ detail, selection, glyphs, data, onSelect, onShow = null, onFrame = null }) {
  const rowHeight = useTreeRowHeight();
  const { selected, select, hover } = selection;
  const picked = useMemo(() => new Set(selected), [selected]);
  const flatPanel = useFlatPanel();
  const refs = useRef({});
  refs.current = { onSelect, onShow, onFrame, page: flatPanel?.page, picked: flatPanel?.picked };
  const choose = useCallback((node, event) => {
    const { onSelect: taken, onShow: show, onFrame: frameIt, page, picked: closed } = refs.current;
    closed?.();
    taken?.();
    select(node.pick, { multiSelect: additive(event) });
    (page ? frameIt : show)?.([node.pick]);
  }, [select]);
  const frame = useCallback(node => refs.current.onFrame?.([node.pick]), []);
  const { rows, facts = [] } = detail;
  const renderRow = at => <MemoDetailRow node={rows[at]} lit={picked.has(rows[at].pick)} choose={choose} frame={frame} hover={hover} glyphs={glyphs} data={data} />;
  // In the panel's detail pane, which pads and scrolls it: what it is reads on the panel's 16px lines,
  // its rows on its 8px one, the "what it is" line under the name, after the glyph slot.
  return <section aria-label={detail.label} className="flex flex-col text-tiny" {...{ [`data-${data}-detail`]: detail.id }}>
    {/* What it is: its name, what that is in words, its facts. */}
    <div className="pt-1.5" data-flat-panel-selected="">
      <TreeRowSurface dense depth={0} className="min-w-0">
        <Glyph kind={detail.kind} glyphs={glyphs} />
        <button type="button" onClick={event => (detail.pick ? choose(detail, event) : null)} onDoubleClick={() => (detail.pick ? frame(detail) : null)}
          className={cn(TREE_ROW_NAME_CLASS, "font-medium")} {...{ [`data-${data}-detail-head`]: detail.id }}>
          <TreeRowLabel className="min-w-0 flex-1">{detail.label}</TreeRowLabel>
        </button>
      </TreeRowSurface>
      {detail.detail ? <p className="truncate pr-2 pb-1 text-micro text-muted-foreground" style={{ paddingLeft: "calc(var(--tree-row-pad, 5px) + 1rem)" }}
        data-flat-panel-selected-what="">{detail.detail}</p> : null}
      {facts.length ? <div className="px-2 pb-1.5" data-flat-panel-facts="">
        {facts.map(fact => <InfoRow key={fact.label} label={fact.label}><MonoValue>{fact.value}</MonoValue></InfoRow>)}
      </div> : null}
    </div>
    {/* What it is connected to: the other pads or pins on its net, or its own; its rule the pane's width. */}
    {rows.length ? <div className="pb-2">
      <h3 className="-mx-2 flex h-6 items-center justify-between gap-2 border-t border-border px-4 text-micro text-muted-foreground"
        data-flat-panel-detail-title="">
        <span className="truncate">{detail.listLabel}</span><span className="shrink-0">{detail.count}</span>
      </h3>
      <VirtualRows key={detail.id} aria-label={detail.listLabel} count={rows.length} rowHeight={rowHeight}
        rowKey={at => rows[at].id} rowProps={() => ({ className: "min-w-0" })} renderRow={renderRow} />
    </div> : null}
  </section>;
}
