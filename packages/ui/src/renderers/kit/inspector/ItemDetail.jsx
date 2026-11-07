import { memo, useCallback, useMemo, useRef } from "react";
import { Check, Copy } from "lucide-react";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import { TREE_GLYPH_STROKE, TREE_ROW_DENSE_ICON_CLASS, TREE_ROW_NAME_CLASS, TreeRowGlyph, TreeRowLabel, TreeRowSurface, useTreeRowHeight } from "@cad/ui/primitives/tree-row";
import { useI18n } from "@cad/ui/i18n";
import { cn } from "@cad/ui/utils";
import { useFlatPanel } from "../shell/FlatPanel.jsx";
import { useCopyFlash } from "./copyFlash.js";
import { selectionItem, useInspect } from "./inspect.js";
import { PickGlyph, hasPickGlyph } from "./pickGlyph.jsx";
import { InfoRow, MonoValue } from "./referenceRows.jsx";
import VirtualRows from "./VirtualRows.jsx";

const EMPTY = Object.freeze([]);
const additive = event => event.shiftKey || event.metaKey || event.ctrlKey;

// The view's panel's two lines (`FlatPanel.jsx`'s), which a card sets for itself: a detail reads the
// same in the pane and in a card.
export const DETAIL_ROW_VARIABLES = Object.freeze({ "--tree-row-pad": "8px", "--tree-row-actions-pad": "6px" });
// A card is read on a rest of the pointer: its list of what the pick is connected to stops at this
// many rows, the rest counted ("+N more"); the pane lists them all.
export const CARD_RELATED_ROWS = 8;
// An ID row is one line of this many characters at most, its middle cut: the whole reference is its
// hint, and what a click on it copies.
export const CARD_ID_CHARS = 28;
export function elideMiddle(text, chars = CARD_ID_CHARS) {
  if (text.length <= chars) return text;
  const head = Math.ceil((chars - 1) / 2), tail = Math.floor((chars - 1) / 2);
  return `${text.slice(0, head)}…${text.slice(text.length - tail)}`;
}

// A kind's glyph: the view's own for it (`glyphs`), else its pick glyph, else the slot alone.
function Glyph({ kind, glyphs }) {
  const Icon = glyphs?.[kind];
  return <TreeRowGlyph>{Icon ? <Icon className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} />
    : hasPickGlyph(kind) ? <PickGlyph kind={kind} className={TREE_ROW_DENSE_ICON_CLASS} /> : null}</TreeRowGlyph>;
}

// One of what it is connected to: its glyph, its name, and its muted detail.
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

const COPY_ICON_CLASS = "size-2.5 shrink-0";
const copyText = copy => (typeof copy === "function" ? copy() : copy);

// Its head: its glyph and its name, and the copy of its reference. In the pane its name picks it again
// (a double-click frames it) and the icon after it copies; in a card the two are one button that copies.
function Head({ item, glyphs, data, copy, onName, onFrameName }) {
  const { t } = useI18n();
  const flash = useCopyFlash();
  const copyable = Boolean(copy) && flash.canCopy;
  const Icon = flash.copied ? Check : Copy;
  const icon = <Icon className={cn(COPY_ICON_CLASS, flash.copied ? "text-foreground" : "text-muted-foreground group-hover/title:text-foreground")} aria-hidden="true" />;
  const label = <TreeRowLabel className="min-w-0">{item.title}</TreeRowLabel>;
  const marks = { [`data-${data}-detail-head`]: item.id };
  return <TreeRowSurface dense depth={0} className="min-w-0" data-detail-head="">
    <Glyph kind={item.kind} glyphs={glyphs} />
    {onName ? <>
      <button type="button" onClick={onName} onDoubleClick={onFrameName} className={cn(TREE_ROW_NAME_CLASS, "flex-initial pr-1 font-medium")} {...marks}>{label}</button>
      {copyable ? <button type="button" aria-label={t("chip.copyReference", { name: item.title })} data-copied={flash.copied ? "" : undefined}
        onClick={() => void flash.copy(copyText(copy))}
        className="group/title mr-2 inline-flex size-4 shrink-0 items-center justify-center rounded-sm outline-none focus-visible:ring-2 focus-visible:ring-ring/45">{icon}</button> : null}
    </> : copyable ? <button type="button" aria-label={t("chip.copyReference", { name: item.title })} data-copied={flash.copied ? "" : undefined}
      onClick={() => void flash.copy(copyText(copy))} {...marks}
      className={cn(TREE_ROW_NAME_CLASS, "group/title flex-initial cursor-pointer font-medium")}>{label}{icon}</button>
      : <span className={cn(TREE_ROW_NAME_CLASS, "font-medium")} {...marks}>{label}</span>}
  </TreeRowSurface>;
}

// Its ID: one line in the monospace face, its middle cut where it is long, the whole of it its hint; a
// click copies its whole reference, what its name copies.
function IdRow({ id, copy }) {
  const { t } = useI18n();
  const shown = elideMiddle(id);
  const value = <span className="inline-block max-w-full whitespace-nowrap align-top font-mono" data-chip-id="">{shown}</span>;
  return <InfoRow label={t("chip.id")} copy={() => copyText(copy) || id}>
    {shown === id ? value : <TooltipHint content={id}>{value}</TooltipHint>}
  </InfoRow>;
}

// Its facts, in their groups: a group ruled off from the one before it, named for assistive technology.
function Facts({ item, copy }) {
  const groups = [];
  for (const fact of item.facts || EMPTY) {
    const last = groups.at(-1);
    if (last && last.section === (fact.section || "")) last.facts.push(fact);
    else groups.push({ section: fact.section || "", facts: [fact] });
  }
  if (!item.ref && !groups.length) return null;
  const row = fact => <InfoRow key={fact.label} label={fact.label} title={fact.title} copy={fact.copy}>
    {typeof fact.value === "string" || typeof fact.value === "number" ? <MonoValue>{fact.value}</MonoValue> : fact.value}
  </InfoRow>;
  return <div className="px-2 pb-1.5" data-flat-panel-facts="">
    {item.ref ? <IdRow id={item.ref} copy={copy} /> : null}
    {groups.map((group, at) => (group.section
      ? <div key={`${group.section}:${at}`} className="mt-1 border-t border-border/60 pt-1" aria-label={group.section} data-detail-section="">{group.facts.map(row)}</div>
      : <div key={`:${at}`} className="contents">{group.facts.map(row)}</div>))}
  </div>;
}

/**
 * What a pick is, drawn ONE way wherever it is read — the Selected pane under the view's panel's lists
 * (`place: "pane"`, `SelectedPane`) and a Quick Edit chip's card (`place: "card"`, `ReferenceChips.jsx`),
 * from the view's data (`inspect.js`'s `DetailItem`), as a CAD tool's Properties panel answers it:
 *
 * - **what it is**: its glyph and name, then its copy (the pane: the name picks it again and a
 *   double-click frames it, the icon after it copies; a card: the name and icon copy); a line in
 *   words (`what`); its ID (`ref`), then its facts, in their groups;
 * - **what it is connected to** (`related`), titled, with its count: a row each, which picks it as a
 *   press on the picture does (Shift, Ctrl or Cmd adds), lit while picked, a double-click framing
 *   it, the pointer on it lighting it. The pane lists every row, mounted as they scroll into view; a
 *   card the first few (`CARD_RELATED_ROWS`), the rest counted.
 *
 * The rows' actions are the view's (`useInspect()`), wherever the detail is drawn.
 *
 * @param {{ item: import("./inspect.js").DetailItem, place?: "pane" | "card",
 *   copy?: string | (() => string) | null }} props
 */
export default function ItemDetail({ item, place = "pane", copy = null }) {
  const { t } = useI18n();
  const inspect = useInspect();
  const rowHeight = useTreeRowHeight();
  const picked = useMemo(() => new Set(inspect?.selected || EMPTY), [inspect?.selected]);
  const flatPanel = useFlatPanel();
  const refs = useRef({});
  refs.current = { inspect, page: flatPanel?.page, closed: flatPanel?.picked };
  const choose = useCallback((node, event) => {
    const { inspect: now, page, closed } = refs.current;
    if (!now || !node.pick) return;
    closed?.();
    now.onSelect?.();
    now.select(node.pick, { multiSelect: additive(event) });
    (page ? now.frame : now.show)?.([node.pick]);
  }, []);
  const frame = useCallback(node => { if (node.pick) refs.current.inspect?.frame?.([node.pick]); }, []);
  const hover = useCallback(pick => refs.current.inspect?.hover?.(pick), []);
  const data = inspect?.data || "item";
  const glyphs = inspect?.glyphs || null;
  const rows = item.related?.rows || EMPTY;
  const card = place === "card";
  const shownRows = card ? rows.slice(0, CARD_RELATED_ROWS) : rows;
  const renderRow = at => <MemoDetailRow node={rows[at]} lit={picked.has(rows[at].pick)} choose={choose} frame={frame} hover={hover} glyphs={glyphs} data={data} />;
  const pane = !card && inspect && item.pick;
  return <section aria-label={item.title} className="flex flex-col text-tiny" data-detail-place={place} {...{ [`data-${data}-detail`]: item.id }}>
    {/* What it is: its name, what that is in words, its ID and its facts. */}
    <div className="pt-1.5" data-flat-panel-selected="">
      <Head item={item} glyphs={glyphs} data={data} copy={copy}
        onName={card ? null : event => (pane ? choose(item, event) : null)} onFrameName={() => (pane ? frame(item) : null)} />
      {item.what ? <p className="truncate pr-2 pb-1 text-micro text-muted-foreground" style={{ paddingLeft: "calc(var(--tree-row-pad, 5px) + 1rem)" }}
        data-flat-panel-selected-what="">{item.what}</p> : null}
      <Facts item={item} copy={copy} />
    </div>
    {/* What it is connected to: its rows, under a rule the width of what it is drawn in. */}
    {rows.length ? <div className="pb-2">
      <h3 className="-mx-2 flex h-6 items-center justify-between gap-2 border-t border-border px-4 text-micro text-muted-foreground"
        data-flat-panel-detail-title="">
        <span className="truncate">{item.related.title}</span><span className="shrink-0">{item.related.count}</span>
      </h3>
      {card ? <div role="list" aria-label={item.related.title}>
        {shownRows.map((node, at) => <div key={node.id} role="listitem" className="min-w-0">{renderRow(at)}</div>)}
        {rows.length > shownRows.length ? <p className="px-4 pt-0.5 text-micro text-muted-foreground" data-detail-more="">
          {t("chip.more", { count: rows.length - shownRows.length })}</p> : null}
      </div> : <VirtualRows key={item.id} aria-label={item.related.title} count={rows.length} rowHeight={rowHeight}
        rowKey={at => rows[at].id} rowProps={() => ({ className: "min-w-0" })} renderRow={renderRow} />}
    </div> : null}
  </section>;
}

/**
 * The Selected pane, every view's that has a panel (`ViewFrame.jsx` hands it to `FlatPanel.jsx`'s
 * `detail`): what is picked, as `ItemDetail` draws it — the one pick, or how many and each of them
 * (`selectionItem`) — its name copying what `copyText` gives. Null while nothing is picked (the
 * panel then draws no pane).
 * @param {import("./inspect.js").Inspect | null} inspect
 */
export function useSelectedDetail(inspect) {
  const { t } = useI18n();
  const selected = inspect?.selected || EMPTY, describe = inspect?.describe, copyOf = inspect?.copyText;
  return useMemo(() => {
    const item = inspect ? selectionItem(inspect, t) : null;
    if (!item) return null;
    const copy = item.pick && copyOf ? copyOf([item.pick]) : "";
    return <ItemDetail item={item} copy={copy || null} />;
    // The pane follows the picks and their description.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected, describe, copyOf, t]);
}
