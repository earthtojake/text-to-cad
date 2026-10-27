import { useI18n } from "@text-to-cad/ui/i18n";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Eye } from "lucide-react";
import { Button } from "@text-to-cad/ui/primitives/button";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import {
  ROW_NAME_UNDER_ACTIONS, TREE_GLYPH_STROKE, TREE_INDENT_PX, TREE_ROW_DENSE_ICON_CLASS, TREE_ROW_INSET_PX, TreeRowChevron, TreeRowGuides,
  TreeRowLabel, TreeRowSurface, treeRowActionsClass, useTreeRowHeight
} from "@text-to-cad/ui/primitives/tree-row";
import { TreeFilterHighlight, TreeFilterInput } from "@text-to-cad/ui/primitives/tree-filter";
import { cn } from "@text-to-cad/ui/utils";
import ToolPanel from "../kit/tools/ToolPanel.jsx";
import { useTreeSearch } from "../kit/inspector/modelTreeSearch.js";
import { openUntilChoice } from "../kit/inspector/treeExpansion.js";
import VirtualRows, { revealRow } from "../kit/inspector/VirtualRows.jsx";
import { NetKindIcon, PadKindIcon, PartKindIcon } from "./boardIcons.jsx";
import { boardTreeAncestors, boardTreeNodeIds, buildBoardTree } from "./boardTree.js";

const EMPTY = Object.freeze([]);
// The room the eye takes at a row's right end: the row's `--row-actions`.
const ROW_ACTIONS_WIDTH = "1.5rem";
// A part or a net can be isolated; a pad is seen with its part, a group is many things.
const isolable = node => node.kind === "part" || node.kind === "net";
// A row's kind, in the glyphs Select's filter names the kinds with: a pad's copper, a part's body and legs, a net's trace.
const KIND_GLYPHS = Object.freeze({ part: PartKindIcon, pad: PadKindIcon, net: NetKindIcon });
function KindGlyph({ kind }) {
  const Glyph = KIND_GLYPHS[kind] || PadKindIcon;
  return <Glyph className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} />;
}
const additive = event => event.shiftKey || event.metaKey || event.ctrlKey;

/**
 * A part's or a net's eye, as a tree row's is: over the row's right end, on hover, kept while it is
 * on. It isolates — everything else on the board steps back — and a press is the eye's alone: it
 * never selects the row.
 */
function IsolateEye({ node, on, onToggle }) {
  const { t } = useI18n();
  const action = on ? t("tree.exitIsolate") : t("tree.isolate");
  return <div data-row-actions="" className={treeRowActionsClass(on)}>
    <TooltipHint content={action}>
      <Button type="button" variant="ghost" size="icon-xs" aria-label={t(on ? "tree.exitIsolateNamed" : "tree.isolateNamed", { name: node.label })} aria-pressed={on}
        className={cn("h-5 w-4", on ? "text-foreground" : "text-muted-foreground")} data-board-isolate={node.id}
        onClick={event => { event.stopPropagation(); onToggle(node.selector); }}>
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

// One row of the tree: a group (Parts, a kind, Nets), a part, a net or a pad, with one glyph in one
// column — a branch's chevron, a pad's own — its name, its muted detail, and a part's or net's eye.
function BoardRow({ node, depth, branch, open, selected, isolated, toggle, choose, hover, onIsolate }) {
  const { t } = useI18n();
  const pickable = node.kind !== "group";
  const eye = isolable(node);
  return <TreeRowSurface dense active={selected} className="group/row relative gap-0 pr-0" data-board-row={node.id}
    style={{ paddingLeft: TREE_ROW_INSET_PX + depth * TREE_INDENT_PX, ...(eye ? { "--row-actions": ROW_ACTIONS_WIDTH } : {}) }}
    onMouseEnter={() => hover(node.selector || "")} onMouseLeave={() => hover("")}>
    <TreeRowGuides depth={depth} inset={TREE_ROW_INSET_PX} />
    {branch ? <button type="button" aria-label={t(open ? "tree.collapse" : "tree.expand", { name: node.label })} aria-expanded={open}
      className="grid h-6 w-3 shrink-0 place-items-center rounded focus-visible:ring-2 focus-visible:ring-ring" onClick={() => toggle(node)}>
      <TreeRowChevron expanded={open} />
    </button> : null}
    <button type="button" aria-label={pickable ? t("tree.select", { name: node.label }) : node.label} aria-pressed={pickable ? selected : undefined}
      onClick={event => (pickable ? choose(node, event) : toggle(node))}
      className={cn("flex h-full min-w-0 flex-1 items-center gap-1 rounded pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        branch && "pl-1", eye && (isolated ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover))}>
      {branch ? null : <KindGlyph kind={node.kind} />}
      <TreeRowLabel className="max-w-full shrink-0">{node.label}</TreeRowLabel>
      {node.detail ? <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{node.detail}</TreeRowLabel> : null}
    </button>
    {eye ? <IsolateEye node={node} on={isolated} onToggle={onIsolate} /> : null}
  </TreeRowSurface>;
}
const MemoBoardRow = memo(BoardRow);

// A search hit is the row without its place in the tree: its name, then what it is under, muted.
function BoardSearchRow({ match, selected, isolated, cursor, choose, hover, onIsolate }) {
  const { t } = useI18n();
  const { entry, indices, alias } = match, { node } = entry;
  const eye = isolable(node);
  return <TreeRowSurface dense active={selected} cursor={cursor} className="group/row relative gap-0 pr-0"
    style={eye ? { "--row-actions": ROW_ACTIONS_WIDTH } : undefined} onMouseEnter={() => hover(node.selector || "")} onMouseLeave={() => hover("")}>
    <button type="button" aria-label={t("tree.select", { name: node.label })} aria-pressed={selected} onClick={event => choose(node, event)} style={{ paddingLeft: TREE_ROW_INSET_PX }}
      className={cn("flex h-full min-w-0 flex-1 items-center gap-1 rounded pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        eye && (isolated ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover))}>
      <KindGlyph kind={node.kind} />
      <TreeRowLabel className="max-w-full shrink-0"><TreeFilterHighlight indices={indices} text={entry.label} /></TreeRowLabel>
      <TreeRowLabel className="flex-1 text-micro text-muted-foreground">
        {alias ? <TreeFilterHighlight indices={alias.indices} text={alias.text} /> : node.detail || entry.prefix.slice(0, -1)}
      </TreeRowLabel>
    </button>
    {eye ? <IsolateEye node={node} on={isolated} onToggle={onIsolate} /> : null}
  </TreeRowSurface>;
}
const MemoBoardSearchRow = memo(BoardSearchRow);

/**
 * A board's **Board**, a section of the file sidebar: its parts by kind, each with its pads, and its
 * nets, each with the pads on it, as a tree is drawn in the sidebar (`settings-ui.md`): headed by its
 * filter, dense rows mounted as they scroll into view (`VirtualRows`). The pointer on a row lights
 * what it names on the board; a press selects it (Shift, Ctrl or Cmd adds or takes away), as a tap
 * on the board does, under any tool; a part's or a net's eye isolates it. It opens as every tree
 * does, until there is a choice (`kit/inspector/treeExpansion.js`): Parts and Nets, a kind with one
 * part, a net with one pad. A pick on the board opens its row's owners and brings it into view,
 * once; from the first row the person opens or shuts, the shape is theirs.
 *
 * @param {{ index: object, selection: ReturnType<typeof import("../kit/tools/select/useSceneSelection.js").useSceneSelection>,
 *   isolated: readonly string[], onIsolate(selector: string): void, onSelect(): void }} props
 *   `onSelect`: a row pressed takes Select up, as a pick in any tree does.
 */
export default function BoardSection({ index, selection, isolated = EMPTY, onIsolate, onSelect }) {
  const { t } = useI18n();
  const tree = useMemo(() => buildBoardTree(index, t), [index, t]);
  const rowHeight = useTreeRowHeight();
  // Untouched, the tree is the rule's shape for the board it shows; the person's from their first change.
  const opened = useMemo(() => openUntilChoice(tree.roots, node => node.children), [tree]);
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
  const highlighted = useMemo(() => new Set(selected.flatMap(boardTreeNodeIds)), [selected]);
  const isolatedIds = useMemo(() => new Set(isolated.flatMap(boardTreeNodeIds)), [isolated]);
  const onSelectRef = useRef(onSelect);
  onSelectRef.current = onSelect;
  const choose = useCallback((node, event) => {
    if (!node.selector) return;
    onSelectRef.current?.();
    select(node.selector, { multiSelect: additive(event) });
  }, [select]);
  const { query, searching, deferredQuery, found, cursorId, listRef, changeQuery, onKeyDown } = useTreeSearch(tree.roots);

  // A pick on the board opens its row's owners, and its row comes into view, once.
  const rowElements = useRef(new Map());
  const registerRow = useCallback((key, element) => { if (element) rowElements.current.set(key, element); else rowElements.current.delete(key); }, []);
  const target = useMemo(() => {
    const last = selected.at(-1);
    return last ? boardTreeNodeIds(last).find(id => tree.nodesById.has(id)) || null : null;
  }, [selected, tree]);
  const revealed = useRef(null);
  useEffect(() => {
    if (!target || searching || revealed.current === target) return;
    const missing = boardTreeAncestors(tree, target).filter(id => !expanded.has(id));
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
    return <MemoBoardRow node={row.node} depth={row.depth} branch={row.branch} open={row.open} selected={highlighted.has(row.node.id)}
      isolated={isolatedIds.has(row.node.id)} toggle={toggle} choose={choose} hover={hover} onIsolate={onIsolate} />;
  };
  const renderSearchRow = at => {
    const match = matches[at], id = match.entry.node.id;
    return <MemoBoardSearchRow match={match} selected={highlighted.has(id)} isolated={isolatedIds.has(id)} cursor={id === cursorId}
      choose={choose} hover={hover} onIsolate={onIsolate} />;
  };
  // Headed by its filter, always there: Escape or its X clears it.
  return <ToolPanel id="board" label={t("board.text.board")} fit="tree" resizable collapsible={false}
    header={<TreeFilterInput label={t("board.text.filter_board")} placeholder={t("tree.filterPlaceholder")} value={query} onChange={changeQuery} onKeyDown={onKeyDown} dense
      yieldWhileTyping className="px-0 shadow-none" />}>
    <div className="flex flex-col text-tiny" aria-label={t("board.text.board_parts_and_nets")}>
      <div ref={listRef} className="px-1 py-1" onClick={event => { if (!event.target.closest("li,button,input")) clear(); }}>
        {searching ? <p role="status" className="px-2 py-1 text-muted-foreground">
          {found.total > matches.length ? t("tree.firstMatches", { shown: matches.length, total: found.total.toLocaleString() }) : t(found.total === 1 ? "tree.match" : "tree.matches", { count: found.total })}
        </p> : null}
        {searching ? matches.length
          ? <VirtualRows key="search" aria-label={t("board.text.board_search_results")} count={matches.length} rowHeight={rowHeight} pinned={searchPinned}
            rowKey={at => matches[at].entry.node.id} rowProps={at => ({ className: "min-w-0", "data-search-row": matches[at].entry.node.id })} renderRow={renderSearchRow} />
          : deferredQuery.trim() ? <p className="px-3 py-6 text-center text-muted-foreground">{t("board.text.nothing_on_the_board_matches_query", { query: deferredQuery.trim() })}</p> : null
        : <VirtualRows key="tree" aria-label={t("board.text.board")} count={rows.length} rowHeight={rowHeight} pinned={treePinned}
          rowKey={at => rows[at].node.id} rowProps={at => ({ className: "min-w-0", "aria-level": rows[at].depth + 1 })}
          renderRow={renderTreeRow} registerRow={registerRow} />}
      </div>
    </div>
  </ToolPanel>;
}
