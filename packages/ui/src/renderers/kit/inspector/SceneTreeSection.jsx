import { useEffect, useMemo, useRef, useState } from "react";
import { Box } from "lucide-react";
import { TREE_GLYPH_STROKE, TREE_ROW_DENSE_ICON_CLASS, TREE_ROW_NAME_CLASS, TreeRowDetail, TreeRowGlyph, TreeRowLabel, TreeRowName, TreeRowSurface, TreeRowToggle } from "@cad/ui/primitives/tree-row";
import { TreeFilterHighlight, TreeSearchStatus } from "@cad/ui/primitives/tree-filter";
import ToolPanel from "../tools/ToolPanel.jsx";
import { useFlatPanel, useFlatPanelSection } from "../shell/FlatPanel.jsx";
import { useTreeSearch } from "./modelTreeSearch.js";
import { revealRow } from "./VirtualRows.jsx";
import { useI18n } from "@cad/ui/i18n";

// A scene's Model tab: the file's tree of nodes (its scene's `nodeTree`) in the view's panel, drawn with the one row
// every list of the panel draws (`primitives/tree-row.jsx`), as the assembly tree is. A node that draws is a part, the
// one Select picks (its `part`): a press on its row picks it as a press on the model does (Shift, Ctrl or Cmd adds), and
// a pick on the model lights its row and brings it into view, its owners opened. A node that only groups is a branch,
// its chevron (and its name) opening it. The panel's search finds a node by its name. These scenes' parts have no
// hiding or isolating of their own, so the rows carry no eye or Isolate.

const EMPTY = Object.freeze([]);
const glyph = Icon => <TreeRowGlyph><Icon className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} /></TreeRowGlyph>;

// Each node's owners, for a pick's reveal.
function ownersOf(roots) {
  const owners = new Map();
  const visit = (nodes, chain) => { for (const node of nodes) { owners.set(node.id, chain); visit(node.children, [...chain, node.id]); } };
  visit(roots, []);
  return owners;
}

function NodeRow({ node, depth, expanded, toggle, highlighted, choose, hover, rowRefs }) {
  const { t } = useI18n();
  const branch = node.children.length > 0, open = expanded.has(node.id);
  // A part picks; a branch opens; a leaf that draws nothing (the one row, the file's, of a scene with none) does neither.
  const press = event => (node.part ? choose(node.part, event) : branch ? toggle(node) : null);
  return <li className="min-w-0">
    <TreeRowSurface ref={element => { if (element) rowRefs.current.set(node.id, element); else rowRefs.current.delete(node.id); }}
      dense depth={depth} active={Boolean(node.part && highlighted.has(node.part))} className="group/row"
      onMouseEnter={() => hover(node.part || "")} onMouseLeave={() => hover("")} data-scene-node={node.id}>
      {branch ? <TreeRowToggle open={open} label={t(open ? "tree.collapse" : "tree.expand", { name: node.label })} onToggle={() => toggle(node)} />
        : node.part ? glyph(Box) : <TreeRowGlyph />}
      <button type="button" aria-label={node.part ? t("tree.select", { name: node.label }) : branch ? t(open ? "tree.collapse" : "tree.expand", { name: node.label }) : node.label}
        aria-pressed={node.part ? highlighted.has(node.part) : undefined} onClick={press} className={TREE_ROW_NAME_CLASS}>
        <TreeRowLabel>{node.label}</TreeRowLabel>
      </button>
    </TreeRowSurface>
    {branch && open ? <ul>{node.children.map(child => <NodeRow key={child.id} {...{ node: child, depth: depth + 1, expanded, toggle, highlighted, choose, hover, rowRefs }} />)}</ul> : null}
  </li>;
}

function NodeSearchRow({ match, highlighted, cursor, choose }) {
  const { t } = useI18n();
  const { entry, indices } = match, { node } = entry;
  const owners = entry.prefix.slice(0, -1);
  return <li className="min-w-0" data-search-row={node.id}>
    <TreeRowSurface dense depth={0} active={Boolean(node.part && highlighted.has(node.part))} cursor={cursor} className="group/row">
      {node.part ? glyph(Box) : <TreeRowGlyph />}
      <button type="button" aria-label={t("tree.select", { name: node.label })} aria-pressed={node.part ? highlighted.has(node.part) : false}
        onClick={event => { if (node.part) choose(node.part, event); }} className={TREE_ROW_NAME_CLASS}>
        <TreeRowName><TreeFilterHighlight indices={indices} text={entry.label} /></TreeRowName>
        {owners ? <TreeRowDetail>{owners}</TreeRowDetail> : null}
      </button>
    </TreeRowSurface>
  </li>;
}

/**
 * @param {{ tree: readonly { id: string, label: string, part: string | null, children: object[] }[] | null,
 *   selection: ReturnType<typeof import("../tools/select/useSceneSelection.js").useSceneSelection>,
 *   onPick?: (() => void) | null, active?: boolean }} props
 *   `onPick`: what a row's press does first (Select taken up, as a pick in a tree does).
 */
export default function SceneTreeSection({ tree, selection, onPick = null, active = true }) {
  const { t } = useI18n();
  const roots = tree || EMPTY;
  const owners = useMemo(() => ownersOf(roots), [roots]);
  // Open at first: the roots, and a chain of single groups under them, so a file opens on its parts.
  const initial = useMemo(() => {
    const open = new Set();
    for (const root of roots) for (let node = root; node && node.children.length;) { open.add(node.id); node = node.children.length === 1 ? node.children[0] : null; }
    return open;
  }, [roots]);
  const [userExpanded, setUserExpanded] = useState(null);
  const expanded = userExpanded || initial;
  const toggle = node => { const next = new Set(expanded); if (!next.delete(node.id)) next.add(node.id); setUserExpanded(next); };
  const highlighted = useMemo(() => new Set(selection.selected), [selection.selected]);
  const choose = (part, event) => { onPick?.(); selection.select(part, { multiSelect: event.ctrlKey || event.metaKey || event.shiftKey }); };

  const flatPanel = useFlatPanel();
  const onScreen = useFlatPanelSection("tree") && active;
  const external = useMemo(() => (flatPanel ? { query: flatPanel.query } : null), [flatPanel?.query]);
  const { searching, found, cursorId, listRef, onKeyDown } = useTreeSearch(roots, external);
  const keys = useRef(onKeyDown);
  keys.current = onKeyDown;
  const registerKeys = flatPanel?.registerKeys;
  useEffect(() => registerKeys?.(event => keys.current(event)), [registerKeys]);

  // A pick on the model opens its row's owners and brings it into view, once, when the list is on screen.
  const rowRefs = useRef(new Map());
  const picked = selection.selected.at(-1) || "";
  const shown = useRef("");
  useEffect(() => {
    if (!picked || shown.current === picked) return;
    const missing = (owners.get(picked) || EMPTY).filter(id => !expanded.has(id));
    if (missing.length) { setUserExpanded(new Set([...expanded, ...missing])); return; }
    if (searching || !onScreen) return;
    const row = rowRefs.current.get(picked);
    if (row && !row.closest("[hidden]")) { revealRow(row); shown.current = picked; }
  }, [picked, owners, expanded, searching, onScreen]);

  return <ToolPanel id="tree" label={t("tree.modelTree")} fit="tree" resizable collapsible={false} hidden={!active}>
    <div className="flex flex-col" aria-label={t("tree.model")}>
      <div ref={listRef} onClick={event => { if (!event.target.closest("li,button,input")) selection.clear(); }}>
        {searching && found.matches.length ? <TreeSearchStatus shown={found.matches.length} total={found.total} hit /> : null}
        {searching ? found.matches.length
          ? <ul aria-label={t("tree.model")}>{found.matches.map(match => <NodeSearchRow key={match.entry.node.id} {...{ match, highlighted, cursor: match.entry.node.id === cursorId, choose }} />)}</ul>
          : null
          : <ul aria-label={t("tree.model")}>{roots.map(node => <NodeRow key={node.id} {...{ node, depth: 0, expanded, toggle, highlighted, choose, hover: selection.hover, rowRefs }} />)}</ul>}
      </div>
    </div>
  </ToolPanel>;
}
