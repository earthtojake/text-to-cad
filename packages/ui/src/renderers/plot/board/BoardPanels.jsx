import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ChevronDown, X } from "lucide-react";
import { TreeRowSurface, TreeRowChevron, TreeRowLabel } from "@text-to-cad/ui/primitives/tree-row";
import { TreeFilterHighlight, TreeFilterInput } from "@text-to-cad/ui/primitives/tree-filter";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuTrigger
} from "@text-to-cad/ui/primitives/dropdown-menu";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { cn } from "@text-to-cad/ui/utils";
import ToolPanel, { ToolPanelClose, ToolPanelFooterButton, TOOL_PANEL_HEADING_TEXT_CLASS } from "../../kit/tools/ToolPanel.jsx";
import { FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { InfoRow } from "../../kit/inspector/referenceRows.jsx";
import { useTreeSearch } from "../../kit/inspector/modelTreeSearch.js";
import { BoardMeasureModeMenu, BoardSelectModeMenu } from "./boardModes.jsx";
import { boardTreeAncestors, boardTreeNodeIds, buildBoardTree } from "./boardTree.js";
import { boardFindingFacts, referenceFacts } from "./boardFacts.js";

const EMPTY = Object.freeze([]);
const NO_IDS = Object.freeze(new Set());
// What the panels call the document they list.
const nounOf = (inspector) => (inspector.document === "schematic" ? "Schematic" : "Board");

function rowActions(node, select) {
  return {
    choose(event) {
      const add = event.ctrlKey || event.metaKey || event.shiftKey;
      if (node.selector) select([node.selector], { add });
    },
  };
}

// A row of the board tree: a group (Parts, a kind, Nets), a part, a net or a pad.
// A board's Nets can be thousands of rows: a row renders again only when it, or a row under it,
// changed (`dirty`: the rows whose highlight or opening changed, and their owners).
// (Named apart from the memo it is wrapped in, so the rows under it are the memo too.)
const BoardRow = memo(function BoardTreeRow({ node, depth, highlighted, expanded, dirty, toggle, select, rowRefs }) {
  const branch = node.children.length > 0;
  const open = branch && expanded.has(node.id);
  const { choose } = rowActions(node, select);
  const pickable = node.kind !== "group";
  return <li className="min-w-0" ref={(element) => { if (element) rowRefs.current.set(node.id, element); else rowRefs.current.delete(node.id); }}>
    <TreeRowSurface dense active={highlighted.has(node.id)} className="gap-0 pr-0" style={{ paddingLeft: depth * 12 }} data-board-row={node.id}>
      {branch ? <button type="button" aria-label={`${open ? "Collapse" : "Expand"} ${node.label}`} aria-expanded={open}
        className="grid h-6 w-4 shrink-0 place-items-center rounded focus-visible:ring-2 focus-visible:ring-ring"
        onClick={() => toggle(node)}><TreeRowChevron expanded={open} dense /></button> : <span className="w-4 shrink-0" />}
      <button type="button" aria-label={pickable ? `Select ${node.label}` : node.label} aria-pressed={pickable ? highlighted.has(node.id) : undefined}
        onClick={pickable ? choose : () => toggle(node)}
        className="flex h-full min-w-0 flex-1 items-center gap-1.5 rounded pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <TreeRowLabel className="max-w-full shrink-0">{node.label}</TreeRowLabel>
        {node.detail ? <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{node.detail}</TreeRowLabel> : null}
      </button>
    </TreeRowSurface>
    {open ? <ul>{node.children.map((child) => <BoardRow key={child.id} {...{ node: child, depth: depth + 1, highlighted, expanded, dirty, toggle, select, rowRefs }} />)}</ul> : null}
  </li>;
}, (before, after) => before.node === after.node && before.depth === after.depth && before.toggle === after.toggle
  && before.select === after.select && !after.dirty.has(after.node.id));

function BoardSearchRow({ match, highlighted, cursor, select }) {
  const { entry, indices, alias } = match;
  const { node } = entry;
  const { choose } = rowActions(node, select);
  return <li className="min-w-0" data-search-row={node.id}>
    <TreeRowSurface dense active={highlighted.has(node.id)} cursor={cursor} className="gap-0 pr-0">
      <button type="button" aria-label={`Select ${node.label}`} aria-pressed={highlighted.has(node.id)} onClick={choose}
        className="flex h-full min-w-0 flex-1 items-center gap-1.5 rounded pl-2 pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <TreeRowLabel className="max-w-full shrink-0"><TreeFilterHighlight indices={indices} text={entry.label} /></TreeRowLabel>
        <TreeRowLabel className="flex-1 text-micro text-muted-foreground">
          {alias ? <TreeFilterHighlight indices={alias.indices} text={alias.text} /> : node.detail || entry.prefix.slice(0, -1)}
        </TreeRowLabel>
      </button>
    </TreeRowSurface>
  </li>;
}

/**
 * Select's panel on a board or a schematic: its parts by kind, each with its pads or pins, and its
 * nets, each with the pads or pins on it. The filter is the top row, with Select's mode menu and the
 * X. It renders again only for what it shows — the document, the selection, the mode — not for
 * every render of the view under it.
 */
export const BoardTreePanel = memo(function BoardTreePanel({ index, documentKind, selection, selectMode, onSelectMode, select, clear, active }) {
  const noun = nounOf({ document: documentKind });
  const tree = useMemo(() => (index ? buildBoardTree(index) : { roots: EMPTY, nodesById: new Map(), parents: new Map() }), [index]);
  const [expanded, setExpanded] = useState(() => new Set(["group:parts"]));
  const toggle = useCallback((node) => setExpanded((current) => {
    const next = new Set(current);
    if (!next.delete(node.id)) next.add(node.id);
    return next;
  }), []);
  const highlighted = useMemo(() => new Set(selection.flatMap(boardTreeNodeIds)), [selection]);
  // The rows whose highlight or opening changed since the rows on screen were drawn, with their owners.
  const drawn = useRef({ tree, highlighted: NO_IDS, expanded: NO_IDS });
  const dirty = useMemo(() => {
    const before = drawn.current;
    const ids = new Set();
    const mark = (id) => { for (let at = id; at && !ids.has(at); at = tree.parents.get(at)) ids.add(at); };
    for (const [now, then] of [[highlighted, before.highlighted], [expanded, before.expanded]]) {
      for (const id of now) if (!then.has(id)) mark(id);
      for (const id of then) if (!now.has(id)) mark(id);
    }
    return ids;
  }, [tree, highlighted, expanded]);
  useEffect(() => { drawn.current = { tree, highlighted, expanded }; });
  const { query, searching, deferredQuery, found, cursorId, listRef, changeQuery, onKeyDown } = useTreeSearch(tree.roots);
  const rowRefs = useRef(new Map());

  // A pick on the board opens its rows' owners, and the last one scrolls into view, once.
  const revealKey = JSON.stringify(selection);
  const revealed = useRef("[]");
  useEffect(() => {
    if (!active || searching || revealed.current === revealKey || !selection.length) return;
    const ids = boardTreeNodeIds(selection.at(-1)).filter((id) => tree.nodesById.has(id));
    if (!ids.length) { revealed.current = revealKey; return; }
    const missing = boardTreeAncestors(tree, ids[0]).filter((id) => !expanded.has(id));
    if (missing.length) { setExpanded((current) => new Set([...current, ...missing])); return; }
    rowRefs.current.get(ids[0])?.scrollIntoView?.({ block: "nearest" });
    revealed.current = revealKey;
  }, [active, searching, revealKey, selection, tree, expanded]);

  return <ToolPanel id="tree" label={noun} fit="tree" resizable closable collapsible={false} hidden={!active}
    header={<TreeFilterInput dense label={`Filter ${noun.toLowerCase()}`} placeholder="Filter…" yieldWhileTyping value={query} onChange={changeQuery} onKeyDown={onKeyDown}
      trailing={<><BoardSelectModeMenu mode={selectMode} onModeChange={onSelectMode} document={documentKind || "board"} /><ToolPanelClose /></>} />}>
    <div className="flex flex-col text-tiny" aria-label={`${noun} parts and nets`}>
      <div ref={listRef} className="px-1 py-1" onClick={(event) => { if (!event.target.closest("li,button,input")) clear(); }}>
        {searching ? <p role="status" className="px-2 py-1 text-micro text-muted-foreground">
          {found.total > found.matches.length ? `First ${found.matches.length} of ${found.total.toLocaleString()} matches` : `${found.total} ${found.total === 1 ? "match" : "matches"}`}
        </p> : null}
        {searching
          ? found.matches.length
            ? <ul aria-label={`${noun} search results`}>{found.matches.map((match) => <BoardSearchRow key={match.entry.node.id} {...{ match, highlighted, cursor: match.entry.node.id === cursorId, select }} />)}</ul>
            : deferredQuery.trim() ? <p className="px-3 py-6 text-center text-tiny text-muted-foreground">{`Nothing matches “${deferredQuery.trim()}”`}</p> : null
          : <ul aria-label={noun}>{tree.roots.map((node) => <BoardRow key={node.id} {...{ node, depth: 0, highlighted, expanded, dirty, toggle, select, rowRefs }} />)}</ul>}
      </div>
    </div>
  </ToolPanel>;
});

// With several references, the heading is a picker over them and the rows are the browsed one's.
function ReferencePicker({ items, browsed, onBrowse }) {
  const current = items[browsed];
  return <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild>
      <button type="button" className={cn("group/picker flex min-w-0 items-center gap-1 text-left", TOOL_PANEL_HEADING_TEXT_CLASS)} aria-label="Choose a reference">
        <span className="min-w-0 truncate">{current.heading}</span>
        <span className="shrink-0 text-muted-foreground tabular-nums">{`${browsed + 1}/${items.length}`}</span>
        <ChevronDown className="size-3 shrink-0 text-muted-foreground opacity-0 group-hover/picker:opacity-100" aria-hidden="true" />
      </button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" sideOffset={4} className={cn(FLOATING_SURFACE_CLASS, "max-w-64")}>
      <DropdownMenuRadioGroup value={String(browsed)} onValueChange={(value) => onBrowse(Number(value))}>
        {items.map((item, at) => <DropdownMenuRadioItem key={item.selector} value={String(at)}>{item.heading}</DropdownMenuRadioItem>)}
      </DropdownMenuRadioGroup>
    </DropdownMenuContent>
  </DropdownMenu>;
}

/**
 * The Reference: what is selected, read back (on a board, in script millimetres). Its heading names
 * it (a picker over several), its X clears the selection, and its foot copies the references (⌘C).
 */
export function BoardReferencePanel({ inspector, active, onCopy, copyShortcut = "" }) {
  const items = useMemo(() => inspector.resolved.map((resolved) => ({ selector: resolved.selector, ...referenceFacts(resolved, inspector.index) })), [inspector.resolved, inspector.index]);
  const [browsed, setBrowsed] = useState(0);
  useEffect(() => { setBrowsed(Math.max(0, items.length - 1)); }, [items.length]);
  const finding = inspector.finding ? boardFindingFacts(inspector.finding, inspector.index) : null;
  if (!items.length && !finding) return null;
  const shown = items[Math.min(browsed, items.length - 1)] || null;
  // A finding is headed by its sentence; what it names is its Items row, and the one thing it names
  // reads below its own rows.
  const title = finding ? finding.heading
    : items.length > 1 ? <ReferencePicker items={items} browsed={Math.min(browsed, items.length - 1)} onBrowse={setBrowsed} /> : shown?.heading;
  const rows = finding ? [...finding.rows, ...(items.length === 1 ? shown.rows : [])] : shown.rows;
  return <ToolPanel id="reference" title={title} label="Reference details" closeLabel="Clear selection" fit="details" resizable hidden={!active}
    onClose={inspector.clear}
    footer={items.length ? <ToolPanelFooterButton label={items.length > 1 ? "Copy All" : "Copy"} shortcut={copyShortcut} onClick={onCopy} /> : null}>
    <div className="px-2 pb-1.5" data-board-reference="">
      {rows.map(([label, value], at) => <InfoRow key={`${label}-${at}`} label={label}><span className="tabular-nums">{value}</span></InfoRow>)}
    </div>
  </ToolPanel>;
}

const ROW = "flex h-6 min-w-0 w-full items-center gap-1.5 rounded-sm px-1 text-micro outline-none";
const length = (value) => `${Number(value).toLocaleString(undefined, { maximumFractionDigits: 3 })} mm`;
const end = (pick) => pick.label || "point";

/** Measure's panel: its snapping in the heading, then each measurement, or a hint before the first. */
export function BoardMeasurePanel({ inspector, shown, onClose }) {
  if (!shown) return null;
  const items = inspector.measurements;
  return <ToolPanel id="measure" title="Measure" label="Measure" collapsible={false} onClose={onClose} closeLabel="Clear measurements"
    actions={<BoardMeasureModeMenu mode={inspector.measureMode} onModeChange={inspector.setMeasureMode} />}>
    {items.length ? <section aria-label="Measurements" className="flex min-w-0 flex-col gap-px px-1 pb-1" role="list">
      {items.map((item, at) => <TooltipHint key={item.id} content={`${end(item.a)} → ${end(item.b)} · dx ${length(item.dx)} · dy ${length(item.dy)}`}>
        <div role="listitem" tabIndex={0} className={cn("group/measure-row cursor-default text-sidebar-foreground/80 hover:bg-sidebar-accent", ROW)}>
          <span className="min-w-0 flex-1 truncate tabular-nums">{length(item.distance)}
            <span className="ml-1.5 text-muted-foreground">{`${end(item.a)} → ${end(item.b)}`}</span></span>
          <button type="button" aria-label={`Delete measurement ${at + 1}`} onClick={() => inspector.removeMeasurement(item.id)}
            className="grid size-4 shrink-0 place-items-center rounded-sm text-muted-foreground opacity-0 transition group-hover/measure-row:opacity-100 focus-visible:opacity-100 hover:text-foreground">
            <X className="size-3" strokeWidth={2} aria-hidden="true" />
          </button>
        </div>
      </TooltipHint>)}
    </section> : <p className="flex min-w-0 flex-col gap-px px-1 pb-1 select-none" data-measure-hint="">
      <span className={cn(ROW, "text-muted-foreground")}>{inspector.measureStart ? `From ${end(inspector.measureStart)}: pick the second point` : "Pick two points to measure"}</span>
    </p>}
  </ToolPanel>;
}
