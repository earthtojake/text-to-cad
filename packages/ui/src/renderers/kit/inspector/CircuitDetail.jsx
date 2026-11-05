import { memo, useCallback, useMemo, useRef } from "react";
import { ScrollArea } from "@cad/ui/primitives/scroll-area";
import { TREE_GLYPH_STROKE, TREE_ROW_DENSE_ICON_CLASS, TREE_ROW_INSET_PX, TreeRowLabel, TreeRowSurface, useTreeRowHeight } from "@cad/ui/primitives/tree-row";
import { cn } from "@cad/ui/utils";
import { useFlatPanel } from "../shell/FlatPanel.jsx";
import VirtualRows from "./VirtualRows.jsx";

const additive = event => event.shiftKey || event.metaKey || event.ctrlKey;

function Glyph({ kind, glyphs }) {
  const Icon = glyphs[kind] || glyphs.pad;
  return <Icon className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} />;
}

// One pad or pin: its glyph, its name (a number under its part, a part and a number under a net), and its muted detail.
function DetailRow({ node, lit, choose, frame, hover, glyphs, data }) {
  return <TreeRowSurface dense active={lit} className="group/row relative gap-0 pr-0" onMouseEnter={() => hover(node.pick)} onMouseLeave={() => hover("")}>
    <button type="button" aria-pressed={lit} onClick={event => choose(node, event)} onDoubleClick={() => frame(node)} {...{ [`data-${data}-detail-row`]: node.id }}
      className="flex h-full min-w-0 flex-1 items-center gap-1 rounded pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      style={{ paddingLeft: TREE_ROW_INSET_PX }}>
      <Glyph kind={node.kind} glyphs={glyphs} />
      <TreeRowLabel className="max-w-full shrink-0">{node.label}</TreeRowLabel>
      {node.detail ? <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{node.detail}</TreeRowLabel> : null}
    </button>
  </TreeRowSurface>;
}
const MemoDetailRow = memo(DetailRow);

/**
 * What is picked, in detail, under a flat view's lists (`FlatPanel.jsx`'s `detail`), as the third of
 * Altium's PCB panel's lists: the picked part's pads or pins, each its number, its pin's name and its
 * net, or the picked net's, each its part and number (`board/boardTree.js`'s `boardDetail`,
 * `schematic/schematicTree.js`'s `schematicDetail`). Its head names what it is the detail of and how
 * many rows it has; the head's name selects it again. A row selects its pad or pin as a press on the
 * picture does (Shift, Ctrl or Cmd adds or takes away), lit while it is selected, and a double-click
 * frames it, as the lists' rows do; the pointer on a row lights it on the picture. A pad picked on the
 * picture shows its part's detail, the pad lit. Its rows are mounted as they scroll into view.
 *
 * @param {{ detail: { id: string, kind: string, pick: string, label: string, detail: string, count: string, listLabel: string,
 *   rows: { id: string, kind: string, pick: string, label: string, detail: string }[] },
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
  const { rows } = detail;
  const renderRow = at => <MemoDetailRow node={rows[at]} lit={picked.has(rows[at].pick)} choose={choose} frame={frame} hover={hover} glyphs={glyphs} data={data} />;
  return <section aria-label={detail.listLabel} className="flex min-h-0 flex-col text-tiny" {...{ [`data-${data}-detail`]: detail.id }}>
    <div className="flex shrink-0 items-center px-2 pt-1.5 pb-1">
      <TreeRowSurface dense active={picked.has(detail.pick)} className="relative min-w-0 flex-1 gap-0 pr-0">
        <button type="button" aria-pressed={picked.has(detail.pick)} onClick={event => choose(detail, event)} onDoubleClick={() => frame(detail)}
          className={cn("flex h-full min-w-0 flex-1 items-center gap-1 rounded pr-2 text-left font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring")}
          style={{ paddingLeft: TREE_ROW_INSET_PX }} {...{ [`data-${data}-detail-head`]: detail.id }}>
          <Glyph kind={detail.kind} glyphs={glyphs} />
          <TreeRowLabel className="max-w-full shrink-0">{detail.label}</TreeRowLabel>
          {detail.detail ? <TreeRowLabel className="min-w-0 flex-1 font-normal text-micro text-muted-foreground">{detail.detail}</TreeRowLabel> : <span className="flex-1" />}
          <span className="shrink-0 font-normal text-micro text-muted-foreground">{detail.count}</span>
        </button>
      </TreeRowSurface>
    </div>
    <ScrollArea className="min-h-0 flex-1">
      <div className="px-2 pb-2">
        <VirtualRows key={detail.id} aria-label={detail.listLabel} count={rows.length} rowHeight={rowHeight}
          rowKey={at => rows[at].id} rowProps={() => ({ className: "min-w-0" })} renderRow={renderRow} />
      </div>
    </ScrollArea>
  </section>;
}
