import { useI18n } from "@cad/ui/i18n";
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Eye } from "lucide-react";
import { Button } from "@cad/ui/primitives/button";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import {
  ROW_NAME_UNDER_ACTIONS, TREE_GLYPH_STROKE, TREE_INDENT_PX, TREE_ROW_DENSE_ICON_CLASS, TREE_ROW_INSET_PX, TreeRowChevron, TreeRowGuides,
  TreeRowLabel, TreeRowSurface, treeRowActionsClass, useTreeRowHeight
} from "@cad/ui/primitives/tree-row";
import { TreeFilterHighlight } from "@cad/ui/primitives/tree-filter";
import { cn } from "@cad/ui/utils";
import { useFlatPanel } from "../shell/FlatPanel.jsx";
import { useTreeSearch } from "./modelTreeSearch.js";
import { openUntilChoice } from "./treeExpansion.js";
import VirtualRows, { revealRow } from "./VirtualRows.jsx";

const EMPTY = Object.freeze([]);
// The room the eye takes at a row's right end: the row's `--row-actions`.
const ROW_ACTIONS_WIDTH = "1.5rem";
// A part or a net can be isolated; a pin or a pad is seen with its part, a group is many things.
const isolable = node => node.kind === "part" || node.kind === "net";
function KindGlyph({ kind, glyphs }) {
  const Glyph = glyphs[kind] || glyphs.pad;
  return <Glyph className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} />;
}
const additive = event => event.shiftKey || event.metaKey || event.ctrlKey;

/**
 * A part's or a net's eye, as a tree row's is: over the row's right end, on hover, kept while it is
 * on. It isolates — everything else on the board steps back — and a press is the eye's alone: it
 * never selects the row.
 */
function IsolateEye({ node, on, onToggle, data }) {
  const { t } = useI18n();
  const action = on ? t("tree.exitIsolate") : t("tree.isolate");
  return <div data-row-actions="" className={treeRowActionsClass(on)}>
    <TooltipHint content={action}>
      <Button type="button" variant="ghost" size="icon-xs" aria-label={t(on ? "tree.exitIsolateNamed" : "tree.isolateNamed", { name: node.label })} aria-pressed={on}
        className={cn("h-5 w-4", on ? "text-foreground" : "text-muted-foreground")} {...{ [`data-${data}-isolate`]: node.id }}
        onClick={event => { event.stopPropagation(); onToggle(node.pick); }}>
        <Eye className="size-3" aria-hidden="true" />
      </Button>
    </TooltipHint>
  </div>;
}

// The tree as the rows it draws, top to bottom: each open branch's children follow it, one level deeper.
function visibleRows(roots, expanded) {
  const rows = [];
  const visit = (nodes, depth) => {
    for (const node of nodes) {
      const branch = node.children.length > 0, open = branch && expanded.has(node.id);
      rows.push({ node, depth, branch, open });
      if (open) visit(node.children, depth + 1);
    }
  };
  visit(roots, 0);
  return rows;
}

// One row of the tree: a block (a schematic sheet, or a kind), a group (Nets), a part, a net or a pad, with one
// glyph in one column — a branch's chevron, a pad's own — its name, its muted detail, and a part's or net's eye.
// A block's name selects every part in it; a group's name is a label, and does nothing. Only a branch's
// chevron opens or shuts it, as the model tree's.
const ROW_NAME_CLASS = "flex h-full min-w-0 flex-1 items-center gap-1 pr-2 text-left";
function RowName({ node }) {
  return <>
    <TreeRowLabel className="max-w-full shrink-0">{node.label}</TreeRowLabel>
    {node.detail ? <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{node.detail}</TreeRowLabel> : null}
  </>;
}
function CircuitRow({ node, depth, branch, open, selected, isolated, toggle, choose, hover, onIsolate, glyphs, data }) {
  const { t } = useI18n();
  const pickable = node.kind !== "group";
  const block = node.kind === "block";
  const eye = isolable(node);
  return <TreeRowSurface dense active={selected} className="group/row relative gap-0 pr-0" {...{ [`data-${data}-row`]: node.id }}
    style={{ paddingLeft: TREE_ROW_INSET_PX + depth * TREE_INDENT_PX, ...(eye ? { "--row-actions": ROW_ACTIONS_WIDTH } : {}) }}
    onMouseEnter={() => hover(node.pick || "")} onMouseLeave={() => hover("")}>
    <TreeRowGuides depth={depth} inset={TREE_ROW_INSET_PX} />
    {branch ? <button type="button" aria-label={t(open ? "tree.collapse" : "tree.expand", { name: node.label })} aria-expanded={open}
      className="grid h-6 w-3 shrink-0 place-items-center rounded focus-visible:ring-2 focus-visible:ring-ring" onClick={() => toggle(node)}>
      <TreeRowChevron expanded={open} />
    </button> : null}
    {pickable ? <button type="button" aria-label={t("tree.select", { name: node.label })} aria-pressed={selected}
      onClick={event => choose(node, event)} {...{ [`data-${data}-block`]: block ? node.id : undefined }}
      className={cn(ROW_NAME_CLASS, "rounded focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        branch && "pl-1", eye && (isolated ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover))}>
      {branch ? null : <KindGlyph kind={node.kind} glyphs={glyphs} />}
      <RowName node={node} />
    </button> : <span className={cn(ROW_NAME_CLASS, "cursor-default", branch && "pl-1")} {...{ [`data-${data}-group`]: node.id }}>
      <RowName node={node} />
    </span>}
    {eye ? <IsolateEye node={node} on={isolated} onToggle={onIsolate} data={data} /> : null}
  </TreeRowSurface>;
}
const MemoCircuitRow = memo(CircuitRow);

// A search hit is the row without its place in the tree: its name, then what it is under, muted.
function CircuitSearchRow({ match, selected, isolated, cursor, choose, hover, onIsolate, glyphs, data }) {
  const { t } = useI18n();
  const { entry, indices, alias } = match, { node } = entry;
  const eye = isolable(node);
  return <TreeRowSurface dense active={selected} cursor={cursor} className="group/row relative gap-0 pr-0"
    style={eye ? { "--row-actions": ROW_ACTIONS_WIDTH } : undefined} onMouseEnter={() => hover(node.pick || "")} onMouseLeave={() => hover("")}>
    <button type="button" aria-label={t("tree.select", { name: node.label })} aria-pressed={selected} onClick={event => choose(node, event)} style={{ paddingLeft: TREE_ROW_INSET_PX }}
      className={cn("flex h-full min-w-0 flex-1 items-center gap-1 rounded pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        eye && (isolated ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover))}>
      <KindGlyph kind={node.kind} glyphs={glyphs} />
      <TreeRowLabel className="max-w-full shrink-0"><TreeFilterHighlight indices={indices} text={entry.label} /></TreeRowLabel>
      <TreeRowLabel className="flex-1 text-micro text-muted-foreground">
        {alias ? <TreeFilterHighlight indices={alias.indices} text={alias.text} /> : node.detail || entry.prefix.slice(0, -1)}
      </TreeRowLabel>
    </button>
    {eye ? <IsolateEye node={node} on={isolated} onToggle={onIsolate} data={data} /> : null}
  </TreeRowSurface>;
}
const MemoCircuitSearchRow = memo(CircuitSearchRow);

/** The rows above a node, outermost first, to open so the node shows. */
export function treeAncestors(tree, id) {
  const chain = [];
  for (let parent = tree.parents.get(id); parent; parent = tree.parents.get(parent)) chain.unshift(parent);
  return chain;
}

/**
 * A **Circuit**, a tab of a flat view's panel (`kit/shell/FlatPanel.jsx`): a board's (`board/BoardSection.jsx`) and a schematic's
 * (`schematic/SchematicSection.jsx`) — its parts in blocks, each part with its pins or pads, then its
 * nets, each with the pins on it — as a tree is drawn in a panel (`settings-ui.md`): dense rows mounted
 * as they scroll into view (`VirtualRows`). The panel's search box searches it: while something is
 * typed, its ranked hits replace its rows (the arrow keys walk them, Enter picks), and with none it
 * draws nothing, so the panel leaves it out. The pointer on a row lights
 * what it names on the picture; a press on a part, a pin or a net selects it (Shift, Ctrl or Cmd adds or
 * takes away), as a click on the picture does, under any tool, and frames it; a press on a block's name
 * selects every part in it, a chip each, and frames them; a part's or a net's eye isolates it. It opens
 * as every tree does, until there is a choice (`treeExpansion.js`), but for a block of several parts and
 * the groups `closedGroups` names (the Nets), shut until the person opens them. Only a row's chevron
 * opens or shuts it, as the model tree's: a block's name selects its parts, a group's is a label. A pick
 * on the picture opens its row's owners and brings it into view, once; a press in the tree opens and
 * scrolls nothing (its row is in view). From the first row the person opens or shuts, the shape is
 * theirs. The viewer is read-only: nothing here edits the file.
 *
 * @param {{ tree: { roots: object[], nodesById: Map<string, object>, parents: Map<string, string> },
 *   nodeIdsOf(id: string): string[], glyphs: Record<string, import("react").ComponentType<any>>,
 *   closedGroups?: readonly string[], data: string, panel: { listLabel: string, treeLabel: string, resultsLabel: string },
 *   selection: ReturnType<typeof import("../tools/select/useSceneSelection.js").useSceneSelection>,
 *   isolated: readonly string[], onIsolate(id: string): void, onSelect(): void, onFrame?(ids: readonly string[]): void }} props
 *   A node names what it picks by `pick` (a block, every part in it, by `picks`). `nodeIdsOf`: the rows a pick's id stands for (a pad shows under its part and under its net); `data`: the rows'
 *   attributes' word (`data-<data>-row`); `onSelect`: a row pressed takes Select up, as a pick in any tree does;
 *   `onFrame`: what a press picked, framed.
 */
export default function CircuitTree({ tree, nodeIdsOf, glyphs, closedGroups = EMPTY, data, panel, selection, isolated = EMPTY, onIsolate, onSelect,
  onFrame = null }) {
  const { t } = useI18n();
  const rowHeight = useTreeRowHeight();
  // Untouched, the tree is the rule's shape for the board it shows; the person's from their first change.
  // A block of more than one part, and the Nets, open when the person opens them: a board's blocks
  // and nets are many, and long.
  const opened = useMemo(() => {
    const open = openUntilChoice(tree.roots, node => node.children);
    for (const node of tree.roots) if (node.kind === "block" && node.children.length > 1) open.delete(node.id);
    for (const id of closedGroups) open.delete(id);
    return open;
  }, [tree, closedGroups]);
  const openedRef = useRef(opened);
  openedRef.current = opened;
  const [touched, setTouched] = useState(null);
  const expanded = touched || opened;
  const reshape = useCallback(change => setTouched(current => change(new Set(current || openedRef.current))), []);
  const toggle = useCallback(node => reshape(next => {
    if (!next.delete(node.id)) next.add(node.id);
    return next;
  }), [reshape]);
  const rows = useMemo(() => visibleRows(tree.roots, expanded), [tree, expanded]);
  const { selected, select, hover, clear } = selection;
  const highlighted = useMemo(() => {
    const rows = new Set(selected.flatMap(nodeIdsOf));
    const picked = new Set(selected);
    // A block is lit while every part in it is selected.
    for (const node of tree.nodesById.values()) if (node.picks?.length && node.picks.every(id => picked.has(id))) rows.add(node.id);
    return rows;
  }, [selected, tree, nodeIdsOf]);
  const isolatedIds = useMemo(() => new Set(isolated.flatMap(nodeIdsOf)), [isolated, nodeIdsOf]);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const onFrameRef = useRef(onFrame);
  onFrameRef.current = onFrame;
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const flatPanel = useFlatPanel();
  const pickedRef = useRef(flatPanel?.picked);
  pickedRef.current = flatPanel?.picked;
  const choose = useCallback((node, event) => {
    // A row pressed: on a phone, the panel gives the view back, the pick on it.
    pickedRef.current?.();
    if (node.picks) {
      // A block: every part in it, one selection, a chip each; with Shift, Ctrl or Cmd, added to what is selected.
      onSelectRef.current?.();
      if (!additive(event)) clear();
      const kept = new Set(additive(event) ? selectedRef.current : []);
      for (const id of node.picks) if (!kept.has(id)) select(id, { multiSelect: true });
      onFrameRef.current?.(node.picks);
      return;
    }
    if (!node.pick) return;
    onSelectRef.current?.();
    select(node.pick, { multiSelect: additive(event) });
    onFrameRef.current?.([node.pick]);
  }, [select, clear]);
  // A press on a tree row picks what is already in view: it opens nothing and scrolls nothing. The
  // selection it makes is marked as the tree's (`pressedInTree`), and the reveal below passes it by.
  const pressedInTree = useRef(false);
  const chooseInTree = useCallback((node, event) => {
    pressedInTree.current = true;
    // Spent by the selection it makes (committed within the press), or, if it made none, at once after.
    setTimeout(() => { pressedInTree.current = false; }, 0);
    choose(node, event);
  }, [choose]);
  const search = useMemo(() => ({ query: flatPanel?.query ?? "" }), [flatPanel?.query]);
  const { searching, found, cursorId, listRef, onKeyDown } = useTreeSearch(tree.roots, search);
  // The panel's search box walks the hits with the arrows and picks with Enter.
  const keysRef = useRef(onKeyDown);
  keysRef.current = onKeyDown;
  const registerKeys = flatPanel?.registerKeys;
  useEffect(() => registerKeys?.(event => keysRef.current(event)), [registerKeys]);

  // A pick on the board opens its row's owners, and its row comes into view, once; a press in the
  // tree (above) does neither. A search hit's press does, once its filter is cleared: its row was not in view.
  const rowElements = useRef(new Map());
  const registerRow = useCallback((key, element) => { if (element) rowElements.current.set(key, element); else rowElements.current.delete(key); }, []);
  const target = useMemo(() => {
    const last = selected.at(-1);
    return last ? nodeIdsOf(last).find(id => tree.nodesById.has(id)) || null : null;
  }, [selected, tree, nodeIdsOf]);
  const revealed = useRef(null);
  useLayoutEffect(() => {
    if (!pressedInTree.current) return;
    pressedInTree.current = false;
    revealed.current = target;
  }, [selected, target]);
  useEffect(() => {
    if (!target || searching || revealed.current === target) return;
    const missing = treeAncestors(tree, target).filter(id => !expanded.has(id));
    if (missing.length) { reshape(next => { for (const id of missing) next.add(id); return next; }); return; }
    const row = rowElements.current.get(target);
    if (row) { revealRow(row); revealed.current = target; }
  }, [target, tree, expanded, searching, reshape]);
  useEffect(() => { if (!target) revealed.current = null; }, [target]);
  const targetIndex = target ? rows.findIndex(row => row.node.id === target) : -1;
  const treePinned = useMemo(() => (targetIndex < 0 ? EMPTY : [targetIndex]), [targetIndex]);
  const matches = found.matches;
  const cursorIndex = searching ? matches.findIndex(match => match.entry.node.id === cursorId) : -1;
  const searchPinned = useMemo(() => (cursorIndex < 0 ? EMPTY : [cursorIndex]), [cursorIndex]);

  const renderTreeRow = at => {
    const row = rows[at];
    return <MemoCircuitRow node={row.node} depth={row.depth} branch={row.branch} open={row.open} selected={highlighted.has(row.node.id)}
      isolated={isolatedIds.has(row.node.id)} toggle={toggle} choose={chooseInTree} hover={hover} onIsolate={onIsolate} glyphs={glyphs} data={data} />;
  };
  const renderSearchRow = at => {
    const match = matches[at], id = match.entry.node.id;
    return <MemoCircuitSearchRow match={match} selected={highlighted.has(id)} isolated={isolatedIds.has(id)} cursor={id === cursorId}
      choose={choose} hover={hover} onIsolate={onIsolate} glyphs={glyphs} data={data} />;
  };
  return <div className="flex flex-col text-tiny" aria-label={panel.listLabel}>
    <div ref={listRef} className="px-2" onClick={event => { if (!event.target.closest("li,button,input")) clear(); }}>
      {searching ? matches.length ? <div data-flat-panel-hit="">
        {found.total > matches.length ? <p role="status" className="px-2 py-1 text-muted-foreground">
          {t("tree.firstMatches", { shown: matches.length, total: found.total.toLocaleString() })}
        </p> : null}
        <VirtualRows key="search" aria-label={panel.resultsLabel} count={matches.length} rowHeight={rowHeight} pinned={searchPinned}
          rowKey={at => matches[at].entry.node.id} rowProps={at => ({ className: "min-w-0", "data-search-row": matches[at].entry.node.id })} renderRow={renderSearchRow} />
      </div> : null
        : <VirtualRows key="tree" aria-label={panel.treeLabel} count={rows.length} rowHeight={rowHeight} pinned={treePinned}
          rowKey={at => rows[at].node.id} rowProps={at => ({ className: "min-w-0", "aria-level": rows[at].depth + 1 })}
          renderRow={renderTreeRow} registerRow={registerRow} />}
    </div>
  </div>;
}
