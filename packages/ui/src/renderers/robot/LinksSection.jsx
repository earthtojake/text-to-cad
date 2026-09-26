import { useEffect, useMemo, useRef, useState } from "react";
import { TreeRowSurface, TreeRowChevron, TreeRowLabel } from "@hardcore/ui/primitives/tree-row";
import { TreeFilterHighlight, TreeFilterInput } from "@hardcore/ui/primitives/tree-filter";
import { cn } from "@hardcore/ui/utils";
import ToolPanel from "../kit/tools/ToolPanel.jsx";
import RobotComponentDetails, { RobotLinkDetails, RobotLinksSummary } from "./LinkDetails.jsx";
import { useTreeSearch } from "../kit/inspector/modelTreeSearch.js";
import { buildRobotTree, robotComponentNodeId, robotLinkFacts, robotLinkNodeId, robotTreeAncestorIds } from "./robotTree.js";

// The robot's kinematic tree, drawn with the Model tree's rows, filter and Reference
// panel: links nest under their parent link through the joint between them (the row's
// muted text), and the named objects inside a link's meshes are its leaves. Two panels of
// the tool stack, on screen while Select is the tool: **Links**, and the **Reference** for
// what is selected.
//
// Expansion starts at the first real choice. The root opens, and so does a chain of
// single links below it (`base_footprint` > `base_link`), because a tree that opens on
// one row answers nothing; everything after that is one click, since a robot the size
// of tom.urdf (78 objects, 51 under one link) is unreadable fully open.

const EMPTY = Object.freeze([]);

function initialExpansion(tree) {
  const expanded = new Set();
  for (const root of tree.roots) {
    for (let node = root; node;) {
      expanded.add(node.id);
      node = node.children.length === 1 && node.children[0].kind === "link" ? node.children[0] : null;
    }
  }
  return expanded;
}

function rowHandlers(node, selection) {
  const link = node.kind === "link";
  return {
    choose: event => (link ? selection.selectLink : selection.select)(link ? node.linkName : node.component.id,
      { multiSelect: event.ctrlKey || event.metaKey || event.shiftKey }),
    enter: () => (link ? selection.hoverLink(node.linkName) : selection.hover(node.component.id)),
    leave: () => (link ? selection.hoverLink("") : selection.hover("")),
  };
}

// Rows carry no icon: every row is a link (a named mesh object is the rare leaf, and
// its place under a link already says what it is), so an icon told nobody anything.
//
// `pinned` is the robot's one root: there is nothing to collapse it into, so it has no
// chevron and takes no indent level — its children start at the tree's left edge, and
// their chevron column is what sets them under it. It is still a row: the root is a
// real link, selectable, and often the one with the base geometry and mass.
function RobotRow({ node, depth = 0, pinned = false, highlighted, expanded, toggle, selection, rowRefs }) {
  const open = pinned || expanded.has(node.id), branch = node.children.length > 0;
  const { choose, enter, leave } = rowHandlers(node, selection);
  return <li className="min-w-0" ref={element => { if (element) rowRefs.current.set(node.id, element); else rowRefs.current.delete(node.id); }}>
    <TreeRowSurface active={highlighted.has(node.id)} className="gap-0 pr-0" style={{ paddingLeft: depth * 12 }}
      onMouseEnter={enter} onMouseLeave={leave}>
      {pinned ? null : branch ? <button type="button" aria-label={`${open ? "Collapse" : "Expand"} ${node.label}`} aria-expanded={open}
        className="grid h-7 w-5 shrink-0 place-items-center rounded focus-visible:ring-2 focus-visible:ring-ring"
        onClick={() => toggle(node)}><TreeRowChevron expanded={open}/></button> : <span className="w-5 shrink-0"/>}
      <button type="button" aria-label={`Select ${node.label}`} aria-pressed={highlighted.has(node.id)}
        onClick={choose} onFocus={enter} onBlur={leave}
        className={cn("flex h-full min-w-0 flex-1 items-center gap-1.5 rounded pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring", pinned && "pl-2")}>
        {/* Name first: in a narrow panel the joint takes the truncation, never the link. */}
        <TreeRowLabel className="max-w-full shrink-0">{node.label}</TreeRowLabel>
        {node.detail && <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{node.detail}</TreeRowLabel>}
      </button>
    </TreeRowSurface>
    {branch && open && <ul>{node.children.map(child => <RobotRow key={child.id} {...{ node: child, depth: pinned ? depth : depth + 1, highlighted, expanded, toggle, selection, rowRefs }}/>)}</ul>}
  </li>;
}

// A search hit is the tree row without its place: the name, then its owners muted —
// or, when the query found the link by its joint, that joint.
function RobotSearchRow({ match, highlighted, cursor, selection }) {
  const { entry, indices, alias } = match, { node } = entry;
  const { choose, enter, leave } = rowHandlers(node, selection);
  const owners = entry.prefix.slice(0, -1);
  return <li className="min-w-0" data-search-row={node.id}>
    <TreeRowSurface active={highlighted.has(node.id)} cursor={cursor} className="gap-0 pr-0" onMouseEnter={enter} onMouseLeave={leave}>
      <button type="button" aria-label={`Select ${node.label}`} aria-pressed={highlighted.has(node.id)} onClick={choose}
        className="flex h-full min-w-0 flex-1 items-center gap-1.5 rounded pl-2 pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
        <TreeRowLabel className="max-w-full shrink-0"><TreeFilterHighlight indices={indices} text={entry.label}/></TreeRowLabel>
        {alias
          ? <TreeRowLabel className="flex-1 text-micro text-muted-foreground"><TreeFilterHighlight indices={alias.indices} text={alias.text}/>{node.joint?.type ? ` · ${node.joint.type}` : ""}</TreeRowLabel>
          : owners && <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{owners}</TreeRowLabel>}
      </button>
    </TreeRowSurface>
  </li>;
}

/**
 * @param {object} props
 * @param {object | null} props.description The parsed robot model (URDF, an SRDF's paired URDF, or SDF).
 * @param {object[]} props.components `buildRobotParts(...).components`: the named mesh objects.
 * @param {{ id: string, linkName: string }[]} props.parts Mesh parts: which viewport geometry belongs to which link.
 * @param {object} props.selection `useLinkSelection`, with `select`/`selectLink` routed through the Select tool.
 * @param {Map<string, string[]> | null} [props.groupNamesByLink] SRDF planning groups per link.
 * @param {boolean} [props.active] Whether Select is the tool, which is when the panels show; a hidden tree does not scroll to a selection.
 * @param {(filename: string) => string} [props.meshPath] The host path of a mesh the description names, or "" when it has none here.
 * @param {(path: string) => void} [props.onOpenFile] Opens a file the description names.
 */
export default function LinksSection({ description = null, components = EMPTY, parts = EMPTY, selection, groupNamesByLink = null, active = true, meshPath = null, onOpenFile = null }) {
  const tree = useMemo(() => buildRobotTree(description, { components, parts }), [description, components, parts]);
  const [userExpanded, setUserExpanded] = useState(null);
  const defaultExpanded = useMemo(() => initialExpansion(tree), [tree]);
  const expanded = userExpanded || defaultExpanded;
  const toggle = node => {
    const next = new Set(expanded);
    if (!next.delete(node.id)) next.add(node.id);
    setUserExpanded(next);
  };

  const selectedNodeIds = useMemo(() => (selection.selectedLinkNames.length
    ? selection.selectedLinkNames.map(robotLinkNodeId)
    : selection.selectedComponentIds.map(robotComponentNodeId)).filter(id => tree.nodesById.has(id)),
  [selection.selectedLinkNames, selection.selectedComponentIds, tree]);
  const highlighted = useMemo(() => new Set(selectedNodeIds), [selectedNodeIds]);

  // Search is a second view of the same tree: typing never touches expansion, and
  // the tree's rows unmount so a large open robot is not re-rendered per keystroke.
  const { query, searching, deferredQuery, found, cursorId, listRef, changeQuery, onKeyDown: onSearchKeyDown } = useTreeSearch(tree.roots);
  const rowRefs = useRef(new Map());

  // A selection is always a row the tree holds: its owners open at once, whether it
  // came from a search hit or from the viewport. The one scroll waits for the tree.
  const revealKey = JSON.stringify(selectedNodeIds);
  const reveal = useRef({ key: "[]", complete: true });
  useEffect(() => {
    if (reveal.current.key !== revealKey) reveal.current = { key: revealKey, complete: !selectedNodeIds.length };
    if (!active || reveal.current.complete) return;
    const missing = selectedNodeIds.flatMap(id => robotTreeAncestorIds(tree, id)).filter(id => !expanded.has(id));
    if (missing.length) { setUserExpanded(new Set([...expanded, ...missing])); return; }
    if (searching) return;
    const row = rowRefs.current.get(selectedNodeIds.at(-1));
    if (row) { row.scrollIntoView?.({ block: "nearest" }); reveal.current.complete = true; }
  }, [active, revealKey, selectedNodeIds, tree, expanded, searching]);


  // One link reads back what the description says of it; several are summarised, as several
  // objects are.
  const shownLinkNames = useMemo(() => selection.selectedLinkNames.filter(name => tree.nodesById.has(robotLinkNodeId(name))),
    [selection.selectedLinkNames, tree]);
  const linkFacts = useMemo(() => (shownLinkNames.length === 1
    ? robotLinkFacts(description, shownLinkNames[0], { groupNamesByLink }) : null),
  [shownLinkNames, description, groupNamesByLink]);
  const selectedComponents = components.filter(component => selection.selectedComponentIds.includes(component.id));
  // The heading names what is selected: one link or object by its name, several by what they are.
  const referenceTitle = shownLinkNames.length === 1 ? shownLinkNames[0] : shownLinkNames.length ? "Links"
    : selectedComponents.length === 1 ? selectedComponents[0].name : "Mesh objects";
  const details = linkFacts ? <RobotLinkDetails facts={linkFacts} meshPath={meshPath} onOpenFile={onOpenFile} onSelectLink={selection.selectLink} hasLinkRow={name => tree.nodesById.has(robotLinkNodeId(name))}/>
    : shownLinkNames.length ? <RobotLinksSummary linkNames={shownLinkNames}/>
    : selection.selectedComponentIds.length ? <RobotComponentDetails components={components} selectedIds={selection.selectedComponentIds}/> : null;
  const clearSelection = () => selection.select("");

  return <>
    {/* No heading: the filter is the panel's top row, and stays put while the tree scrolls under it. */}
    <ToolPanel label="Links" fit="tree" hidden={!active}
      header={<TreeFilterInput className="px-1" label="Filter links" placeholder="Filter links…" value={query} onChange={changeQuery} onKeyDown={onSearchKeyDown}/>}>
      <div className="flex flex-col text-xs" aria-label="Robot links">
        <div ref={listRef} className="px-1 py-1" aria-label="Robot tree area"
          onClick={event => { if (!event.target.closest("li,button,input")) clearSelection(); }}>
          {searching && <p role="status" className="px-2 py-1 text-micro text-muted-foreground">{found.total > found.matches.length ? `First ${found.matches.length} of ${found.total.toLocaleString()} matches` : `${found.total} ${found.total === 1 ? "match" : "matches"}`}</p>}
          {searching ? found.matches.length
            ? <ul aria-label="Link search results">{found.matches.map(match => <RobotSearchRow key={match.entry.node.id} {...{ match, highlighted, cursor: match.entry.node.id === cursorId, selection }}/>)}</ul>
            : deferredQuery.trim() && <p className="px-3 py-6 text-center text-xs text-muted-foreground">{`No link matches “${deferredQuery.trim()}”`}</p>
          : tree.roots.length
            ? <ul aria-label="Robot links">{tree.roots.map(node => <RobotRow key={node.id} pinned={tree.roots.length === 1 && node.children.length > 0} {...{ node, highlighted, expanded, toggle, selection, rowRefs }}/>)}</ul>
            : <p role="status" className="p-2 text-tiny text-muted-foreground">{description ? "This description has no links." : "Loading links…"}</p>}
        </div>
      </div>
    </ToolPanel>
    {details ? <ToolPanel title={referenceTitle} label="Reference details" closeLabel="Clear selection" fit="details" capped hidden={!active} onClose={clearSelection}>
      <div className="px-2 pb-2">{details}</div>
    </ToolPanel> : null}
  </>;
}
