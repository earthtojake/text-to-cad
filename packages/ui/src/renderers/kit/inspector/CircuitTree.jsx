import { useI18n } from "@cad/ui/i18n";
import { memo, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Eye } from "lucide-react";
import { Button } from "@cad/ui/primitives/button";
import { TooltipHint } from "@cad/ui/primitives/tooltip";
import {
  ROW_NAME_UNDER_ACTIONS, TREE_GLYPH_STROKE, TREE_ROW_DENSE_ICON_CLASS, TREE_ROW_NAME_CLASS, TreeRowActions, TreeRowGlyph,
  TreeRowLabel, TreeRowSurface, TreeRowToggle, useTreeRowHeight
} from "@cad/ui/primitives/tree-row";
import { TreeFilterHighlight } from "@cad/ui/primitives/tree-filter";
import { cn } from "@cad/ui/utils";
import { ContextMenu, ContextMenuContent, ContextMenuItem, ContextMenuSeparator, ContextMenuTrigger } from "@cad/ui/primitives/context-menu";
import { useFlatPanel } from "../shell/FlatPanel.jsx";
import { ViewMenuItems, menuEntry, menuGroups, pickGroup } from "../shell/viewMenu.js";
import { useTreeSearch } from "./modelTreeSearch.js";
import { openUntilChoice } from "./treeExpansion.js";
import VirtualRows, { revealRow } from "./VirtualRows.jsx";

const EMPTY = Object.freeze([]);
const NONE = new Set();
// A part or a net can be isolated; a pin or a pad is seen with its part, a group is many things.
const isolable = node => node.kind === "part" || node.kind === "net";
function KindGlyph({ kind, glyphs }) {
  const Glyph = glyphs[kind] || glyphs.pad;
  return <TreeRowGlyph><Glyph className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} /></TreeRowGlyph>;
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
  return <TreeRowActions persistent={on}>
    <TooltipHint content={action}>
      <Button type="button" variant="ghost" size="icon-xs" aria-label={t(on ? "tree.exitIsolateNamed" : "tree.isolateNamed", { name: node.label })} aria-pressed={on}
        className={cn("h-5 w-4", on ? "text-foreground" : "text-muted-foreground")} {...{ [`data-${data}-isolate`]: node.id }}
        onClick={event => { event.stopPropagation(); onToggle(node.pick); }}>
        <Eye className="size-3" aria-hidden="true" />
      </Button>
    </TooltipHint>
  </TreeRowActions>;
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

// One row of a list: a block (a schematic sheet, or a kind), a group (the unconnected pins), a part or a net, with one
// glyph in its slot — a branch's chevron, a leaf's own — its name, its muted detail, and a part's or net's eye.
// A block's name opens or shuts it, as a folder's (its menu's Select all parts selects every part in it), and so
// does a press on its chevron; a group's name is a label, and does nothing. Any other branch opens or shuts by
// its chevron, as the model tree's.
function RowName({ node }) {
  return <>
    <TreeRowLabel className="max-w-full shrink-0">{node.label}</TreeRowLabel>
    {node.detail ? <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{node.detail}</TreeRowLabel> : null}
  </>;
}
/** A row's menu, built as it opens (`menuOf`, every view's groups): a tree of rows never pays for it. */
function RowMenu({ node, menuOf, children }) {
  const [open, setOpen] = useState(false);
  if (!menuOf) return children;
  return <ContextMenu onOpenChange={setOpen}><ContextMenuTrigger asChild>{children}</ContextMenuTrigger>
    <ContextMenuContent className="w-44">
      {open ? <ViewMenuItems entries={menuOf(node)} Item={ContextMenuItem} Separator={ContextMenuSeparator} /> : null}
    </ContextMenuContent>
  </ContextMenu>;
}

function CircuitRow({ node, depth, branch, open, selected, holds, isolated, toggle, choose, frame, hover, onIsolate, glyphs, data, menuOf }) {
  const { t } = useI18n();
  const block = node.kind === "block";
  const pickable = node.kind !== "group" && !block;
  const eye = isolable(node);
  const toggleLabel = t(open ? "tree.collapse" : "tree.expand", { name: node.label });
  return <RowMenu node={node} menuOf={node.kind === "group" ? null : menuOf}><TreeRowSurface dense depth={depth} actions={eye ? 1 : 0} active={selected} cursor={holds}
    className="group/row" {...{ [`data-${data}-row`]: node.id }} data-holds-selection={holds ? "" : undefined}
    onMouseEnter={() => hover(node.pick || "")} onMouseLeave={() => hover("")}>
    {/* A block's chevron is its name's button's too: the pointer's, the keyboard's way in being the name. */}
    {branch ? <TreeRowToggle open={open} label={toggleLabel} mark={block} onToggle={() => toggle(node)} /> : <KindGlyph kind={node.kind} glyphs={glyphs} />}
    {pickable ? <button type="button" aria-label={t("tree.select", { name: node.label })} aria-pressed={selected}
      onClick={event => choose(node, event)} onDoubleClick={() => frame(node)}
      className={cn(TREE_ROW_NAME_CLASS, eye && (isolated ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover))}>
      <RowName node={node} />
    </button> : block ? <button type="button" aria-label={toggleLabel} aria-expanded={open}
      onClick={() => toggle(node)} {...{ [`data-${data}-block`]: node.id }} className={TREE_ROW_NAME_CLASS}>
      <RowName node={node} />
    </button> : <span className={cn(TREE_ROW_NAME_CLASS, "cursor-default")} {...{ [`data-${data}-group`]: node.id }}>
      <RowName node={node} />
    </span>}
    {eye ? <IsolateEye node={node} on={isolated} onToggle={onIsolate} data={data} /> : null}
  </TreeRowSurface></RowMenu>;
}
const MemoCircuitRow = memo(CircuitRow);

// A search hit is the row without its place in the tree: its name, then what it is under, muted.
function CircuitSearchRow({ match, selected, isolated, cursor, choose, frame, hover, onIsolate, glyphs, data, menuOf }) {
  const { t } = useI18n();
  const { entry, indices, alias } = match, { node } = entry;
  const eye = isolable(node);
  return <RowMenu node={node} menuOf={menuOf}><TreeRowSurface dense depth={0} actions={eye ? 1 : 0} active={selected} cursor={cursor} className="group/row"
    onMouseEnter={() => hover(node.pick || "")} onMouseLeave={() => hover("")}>
    <KindGlyph kind={node.kind} glyphs={glyphs} />
    <button type="button" aria-label={t("tree.select", { name: node.label })} aria-pressed={selected} onClick={event => choose(node, event)} onDoubleClick={() => frame(node)}
      className={cn(TREE_ROW_NAME_CLASS, eye && (isolated ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover))}>
      <TreeRowLabel className="max-w-full shrink-0"><TreeFilterHighlight indices={indices} text={entry.label} /></TreeRowLabel>
      <TreeRowLabel className="flex-1 text-micro text-muted-foreground">
        {alias ? <TreeFilterHighlight indices={alias.indices} text={alias.text} /> : node.detail || entry.prefix.slice(0, -1)}
      </TreeRowLabel>
    </button>
    {eye ? <IsolateEye node={node} on={isolated} onToggle={onIsolate} data={data} /> : null}
  </TreeRowSurface></RowMenu>;
}
const MemoCircuitSearchRow = memo(CircuitSearchRow);

/** The rows above a node, outermost first, to open so the node shows. */
export function treeAncestors(tree, id) {
  const chain = [];
  for (let parent = tree.parents.get(id); parent; parent = tree.parents.get(parent)) chain.unshift(parent);
  return chain;
}

/**
 * A list of a flat view's panel (`kit/shell/FlatPanel.jsx`): a board's or a schematic's **Parts**, in
 * blocks, or its **Nets** (`board/BoardSection.jsx`, `schematic/SchematicSection.jsx`), as Altium's
 * PCB panel lists Components and Nets — a part's pins or pads are not rows here, they are what the
 * picked part shows under the lists (the Selected pane, `ItemDetail.jsx`). It is drawn as a tree is in a panel
 * (`settings-ui.md`): dense rows mounted as they scroll into view (`VirtualRows`). The panel's search
 * box searches it (`searchRoots`, the list with what it holds: a part's pads, so `#U3.9` finds one):
 * while something is typed, its ranked hits replace its rows (the arrow keys walk them while its tab is
 * open, Enter picks), and with none it draws nothing, so the panel leaves it out. The pointer on a row
 * lights what it names on the picture; a press on a part, a pin or a net selects it (Shift, Ctrl or Cmd
 * adds or takes away), as a click on the picture does, under any tool, and shows it where it is
 * (`onShow`: a schematic's other sheet); a double-click frames it (`onFrame`), as KiCad's and Altium's
 * lists zoom to what is double-clicked. On a phone a press frames it too, as the page gives the view
 * back. A press on a block's name opens or shuts it, as a folder's; its row menu's Select all parts
 * selects every part in it (Quick Edit's one chip for the block). Every row but a group's has the view's menu
 * (`kit/shell/viewMenu.js`: the reference, Select, Isolate, Zoom to it); a part's or a net's eye
 * isolates it. It opens as every tree does, until there is a choice (`treeExpansion.js`), but for a
 * block of several parts and the groups `closedGroups` names, shut until the person opens them. A
 * row's chevron opens or shuts it, and a block's name does too; a group's is a label. From the first row
 * the person opens or shuts, the shape is theirs. A pick made anywhere but in the list (on the picture,
 * in the Selected pane, a search hit's, a host's) brings its row into view, once a pick, as the model
 * tree's does: its own row, else the row it is under (`ownerOf`: a pad's or a pin's part in the Parts,
 * the net of what is on one in the Nets), which is tinted while it holds the pick, as a selected row is
 * lit; a pick with no row moves nothing, and a press in the list
 * opens and scrolls nothing (its row is in view). One block follows the pick: what a reveal opens is
 * kept apart from the person's shape (`followed`), and the next reveal that goes elsewhere shuts it
 * again, as does nothing being selected, so the list is the shape the person left and at most the one
 * chain the latest pick opened. A
 * block of that chain the person opens or shuts is theirs from then on. Only a list on screen follows
 * (`useFlatPanel()`'s `shown`, its rows not stepped aside for a search): one hidden, or under a
 * collapsed panel, waits, and reveals the pick's row once it is shown. The viewer is read-only:
 * nothing here edits the file.
 *
 * @param {{ tree: { roots: object[], nodesById: Map<string, object>, parents: Map<string, string> }, searchRoots?: object[],
 *   nodeIdsOf(id: string): string[], ownerOf?(id: string): string[], glyphs: Record<string, import("react").ComponentType<any>>,
 *   closedGroups?: readonly string[], data: string, panel: { listLabel: string, treeLabel: string, resultsLabel: string },
 *   selection: ReturnType<typeof import("../tools/select/useSceneSelection.js").useSceneSelection>,
 *   isolated: readonly string[], onIsolate(id: string): void, onSelect(): void, onShow?(ids: readonly string[]): void,
 *   onFrame?(ids: readonly string[]): void }} props
 *   A node names what it picks by `pick` (a block, every part in it, by `picks`). `nodeIdsOf`: the rows a pick's id is;
 *   `ownerOf`: the rows it is under, for one with none of its own; `data`: the rows' attributes' word (`data-<data>-row`);
 *   `onSelect`: a row pressed takes Select up, as a pick in any tree does.
 */
export default function CircuitTree({ tree, searchRoots = null, nodeIdsOf, ownerOf = null, glyphs, closedGroups = EMPTY, data, panel, selection,
  isolated = EMPTY, onIsolate, onSelect, onShow = null, onFrame = null, onCopyReference = null }) {
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
  const shape = touched || opened;
  // What the latest reveal opened that the person's shape has shut (below): open over it, never in it.
  const [followed, setFollowed] = useState(NONE);
  const followedRef = useRef(followed);
  followedRef.current = followed;
  const expanded = useMemo(() => (followed.size ? new Set([...shape, ...followed]) : shape), [shape, followed]);
  const reshape = useCallback(change => setTouched(current => change(new Set(current || openedRef.current))), []);
  const toggle = useCallback(node => {
    // A row a reveal opened, shut by the person: theirs from now, shut, and no longer followed.
    if (followedRef.current.has(node.id)) {
      setFollowed(current => new Set([...current].filter(id => id !== node.id)));
      reshape(next => { next.delete(node.id); return next; });
      return;
    }
    reshape(next => {
      if (!next.delete(node.id)) next.add(node.id);
      return next;
    });
  }, [reshape]);
  const rows = useMemo(() => visibleRows(tree.roots, expanded), [tree, expanded]);
  const { selected, select, hover, clear } = selection;
  const highlighted = useMemo(() => {
    const rows = new Set(selected.flatMap(nodeIdsOf));
    const picked = new Set(selected);
    // A block is lit while every part in it is selected.
    for (const node of tree.nodesById.values()) if (node.picks?.length && node.picks.every(id => picked.has(id))) rows.add(node.id);
    return rows;
  }, [selected, tree, nodeIdsOf]);
  // The rows that hold what is selected without being it (a pad's or a pin's part, the net of what is on
  // one): tinted, not lit, so the row a pick's reveal lands on says why.
  const holding = useMemo(() => {
    if (!ownerOf) return NONE;
    const has = id => tree.nodesById.has(id);
    const rows = new Set();
    for (const id of selected) if (!nodeIdsOf(id).some(has)) for (const owner of ownerOf(id)) if (has(owner)) rows.add(owner);
    return rows;
  }, [selected, tree, nodeIdsOf, ownerOf]);
  const isolatedIds = useMemo(() => new Set(isolated.flatMap(nodeIdsOf)), [isolated, nodeIdsOf]);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const onFrameRef = useRef(onFrame);
  onFrameRef.current = onFrame;
  const onShowRef = useRef(onShow);
  onShowRef.current = onShow;
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const flatPanel = useFlatPanel();
  const pickedRef = useRef(flatPanel?.picked);
  pickedRef.current = flatPanel?.picked;
  const pageRef = useRef(flatPanel?.page);
  pageRef.current = flatPanel?.page;
  // What a press picked, shown: framed on a phone, whose page gives the view back; elsewhere where it is.
  const shown = picks => (pageRef.current ? onFrameRef.current : onShowRef.current)?.(picks);
  const frame = useCallback(node => {
    const picks = node.picks || (node.pick ? [node.pick] : null);
    if (picks?.length) onFrameRef.current?.(picks);
  }, []);
  const choose = useCallback((node, event) => {
    // A row pressed: on a phone, the panel gives the view back, the pick on it.
    pickedRef.current?.();
    if (node.picks) {
      // A block: every part in it, one selection, a chip each; with Shift, Ctrl or Cmd, added to what is selected.
      onSelectRef.current?.();
      if (!additive(event)) clear();
      const kept = new Set(additive(event) ? selectedRef.current : []);
      for (const id of node.picks) if (!kept.has(id)) select(id, { multiSelect: true });
      shown(node.picks);
      return;
    }
    if (!node.pick) return;
    onSelectRef.current?.();
    select(node.pick, { multiSelect: additive(event) });
    shown([node.pick]);
  }, [select, clear]);
  // A row's menu, every view's groups (`kit/shell/viewMenu.js`): a block's Select all parts and its
  // framing; a part's, a pad's or a net's reference (with what is selected), Select or Deselect, Isolate, and its framing.
  const isolatedRef = useRef(isolated);
  isolatedRef.current = isolated;
  const copyRef = useRef(onCopyReference);
  copyRef.current = onCopyReference;
  // A press on a tree row, or its menu, picks what is already in view: it opens nothing and scrolls
  // nothing. The selection it makes is marked as the list's (`pressedInTree`), and the reveal below passes it by.
  const pressedInTree = useRef(false);
  const inTree = useCallback(pick => {
    pressedInTree.current = true;
    // Spent by the selection it makes (committed within the press), or, if it made none, at once after.
    setTimeout(() => { pressedInTree.current = false; }, 0);
    pick();
  }, []);
  const chooseInTree = useCallback((node, event) => inTree(() => choose(node, event)), [inTree, choose]);
  const menuOf = useCallback(node => {
    const zoom = [menuEntry("zoom-to", t("menu.zoomToNamed", { name: node.label }), { onSelect: () => frame(node) })];
    if (node.picks) return menuGroups([menuEntry("select-all", t("menu.selectAllParts", { count: node.picks.length }), { onSelect: () => chooseInTree(node, {}) })], zoom);
    if (!node.pick) return [];
    const picked = selectedRef.current.includes(node.pick);
    return menuGroups(
      copyRef.current ? [menuEntry("copy-reference", t("menu.copyReference"), { onSelect: () => copyRef.current([...new Set([...selectedRef.current, node.pick])]) })] : [],
      pickGroup({ selected: picked, t, onSelect: () => inTree(() => { onSelectRef.current?.(); select(node.pick, { multiSelect: picked }); }),
        isolated: isolable(node) ? isolatedRef.current.includes(node.pick) : null, onIsolate: () => onIsolate(node.pick) }),
      zoom);
  }, [t, frame, chooseInTree, inTree, select, onIsolate]);
  const search = useMemo(() => ({ query: flatPanel?.query ?? "" }), [flatPanel?.query]);
  const { searching, found, cursorId, listRef, onKeyDown } = useTreeSearch(searchRoots || tree.roots, search);
  // The panel's search box walks the hits with the arrows and picks with Enter.
  const keysRef = useRef(onKeyDown);
  keysRef.current = onKeyDown;
  const registerKeys = flatPanel?.registerKeys;
  useEffect(() => registerKeys?.(event => keysRef.current(event)), [registerKeys]);

  // A pick made anywhere but here brings its row into view, once: its own row, else the one it is under.
  // The rows above it that the person's shape has shut open as the one chain followed, which shuts the
  // last pick's chain; a press in the list (above) is marked revealed as it is made, and moves nothing.
  // Nothing selected shuts what the last reveal opened, the person's shape left as it is; a pick with no
  // row here leaves it open.
  const rowElements = useRef(new Map());
  const registerRow = useCallback((key, element) => { if (element) rowElements.current.set(key, element); else rowElements.current.delete(key); }, []);
  const target = useMemo(() => {
    const last = selected.at(-1);
    if (!last) return null;
    const has = id => tree.nodesById.has(id);
    return nodeIdsOf(last).find(has) || ownerOf?.(last).find(has) || null;
  }, [selected, tree, nodeIdsOf, ownerOf]);
  const revealed = useRef(null);
  useLayoutEffect(() => {
    if (!pressedInTree.current) return;
    pressedInTree.current = false;
    revealed.current = target;
  }, [selected, target]);
  // A list on screen follows: its tab the one shown, its panel open, its rows not stepped aside for a search.
  const following = flatPanel?.shown !== false && !searching;
  const nothing = selected.length === 0;
  useEffect(() => { if (nothing) setFollowed(NONE); }, [nothing]);
  useEffect(() => {
    if (!target) { revealed.current = null; return; }
    if (!following || revealed.current === target) return;
    const chain = treeAncestors(tree, target).filter(id => !shape.has(id));
    if (chain.length !== followed.size || chain.some(id => !followed.has(id))) { setFollowed(chain.length ? new Set(chain) : NONE); return; }
    const row = rowElements.current.get(target);
    if (row) { revealRow(row); revealed.current = target; }
  }, [target, tree, shape, followed, following]);
  const targetIndex = target ? rows.findIndex(row => row.node.id === target) : -1;
  const treePinned = useMemo(() => (targetIndex < 0 ? EMPTY : [targetIndex]), [targetIndex]);
  const matches = found.matches;
  const cursorIndex = searching ? matches.findIndex(match => match.entry.node.id === cursorId) : -1;
  const searchPinned = useMemo(() => (cursorIndex < 0 ? EMPTY : [cursorIndex]), [cursorIndex]);

  const renderTreeRow = at => {
    const row = rows[at];
    return <MemoCircuitRow node={row.node} depth={row.depth} branch={row.branch} open={row.open} selected={highlighted.has(row.node.id)}
      holds={holding.has(row.node.id)} isolated={isolatedIds.has(row.node.id)} toggle={toggle} choose={chooseInTree} frame={frame} hover={hover} onIsolate={onIsolate} glyphs={glyphs} data={data} menuOf={menuOf} />;
  };
  const renderSearchRow = at => {
    const match = matches[at], id = match.entry.node.id;
    return <MemoCircuitSearchRow match={match} selected={highlighted.has(id)} isolated={isolatedIds.has(id)} cursor={id === cursorId}
      choose={choose} frame={frame} hover={hover} onIsolate={onIsolate} glyphs={glyphs} data={data} menuOf={menuOf} />;
  };
  return <div className="flex flex-col text-tiny" aria-label={panel.listLabel}>
    <div ref={listRef} onClick={event => {
      // A row menu's item is a portal's: its click reaches here through React, from outside the list.
      if (event.currentTarget.contains(event.target) && !event.target.closest("li,button,input")) clear();
    }}>
      {searching ? matches.length ? <div data-flat-panel-hit="">
        {found.total > matches.length ? <p role="status" className="px-2 py-1 text-muted-foreground" data-tree-status="">
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
