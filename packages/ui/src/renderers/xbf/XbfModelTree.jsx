import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Box, Boxes, Focus } from 'lucide-react';
import { Button } from '@text-to-cad/ui/primitives/button';
import { ROW_NAME_UNDER_ACTIONS, TREE_GLYPH_STROKE, TREE_INDENT_PX, TREE_ROW_INSET_PX, TREE_ROW_DENSE_ICON_CLASS, TreeRowSurface, useTreeRowHeight, TreeRowChevron, TreeRowGuides, TreeRowLabel } from '@text-to-cad/ui/primitives/tree-row';
import { TreeFilterHighlight, TreeFilterInput } from '@text-to-cad/ui/primitives/tree-filter';
import { cn } from '@text-to-cad/ui/utils';
import XbfPartMenu from './XbfPartMenu.jsx';
import XbfPartActions, { rowActionsLayout } from './XbfPartActions.jsx';
import ToolPanel from '../kit/tools/ToolPanel.jsx';
import { modelTreeSearchChain, useTreeSearch } from '../kit/inspector/modelTreeSearch.js';
import VirtualRows, { revealRow } from '../kit/inspector/VirtualRows.jsx';
import { implicitXbfRoots, xbfSelectionPaths } from './xbfTree.js';

// An engine document's Model tree, as the STEP renderer's was, over the engine's tree as
// `xbfTree.js` presents it. An engine document's faces and edges are always to hand, so no row asks
// for a part's topology and the tree never says "Loading…".

const EMPTY = [];
const NO_CONTROLS = {};
const icons = {part:Box,assembly:Boxes,group:Boxes};

// What hides a row or puts it out of reach, as sets: `availabilityOf(partControls)`.
function availabilityOf(hiddenPartIds, selectableNodeIds) {
  return { hidden: new Set(hiddenPartIds || EMPTY), selectable: selectableNodeIds ? new Set(selectableNodeIds) : null };
}
function nodeAvailability(node, availability, inheritedHidden=false, inheritedUnavailable=false) {
  const hidden = node.leafPartIds?.length > 0 && node.leafPartIds.every(id => availability.hidden.has(id));
  const hiddenByOwner = inheritedHidden || hidden;
  const outsideFrontier = node.selectionId
    ? Boolean(availability.selectable) && !availability.selectable.has(node.selectionId)
    : inheritedUnavailable;
  return {hiddenByOwner,outsideFrontier,unavailable:hiddenByOwner || outsideFrontier};
}

// Selected rows that touch read as ONE block: a run of consecutive visible selected rows is
// rounded only at its top and bottom, so a multi-select is a unit rather than a stack of pills.
function joinedCorners(above, below) {
  if (!above && !below) return undefined;
  return {
    ...(above ? { borderTopLeftRadius: 0, borderTopRightRadius: 0 } : {}),
    ...(below ? { borderBottomLeftRadius: 0, borderBottomRightRadius: 0 } : {}),
  };
}
// The tree as the rows it draws, top to bottom: each open branch's children follow it, one
// level deeper. A row carries what it inherits from its owners.
function visibleRows(roots, expanded, availability, owner) {
  const rows = [], keys = new Set();
  const visit = (nodes, depth, inheritedHidden, inheritedUnavailable) => {
    for (const node of nodes) {
      const children = node.children || EMPTY;
      const open = expanded.has(node.id);
      const branch = children.length > 0;
      const {hiddenByOwner,outsideFrontier,unavailable}=nodeAvailability(node,availability,inheritedHidden,inheritedUnavailable);
      const key = keys.has(node.id) ? `${node.id}#${rows.length}` : node.id;
      keys.add(node.id);
      rows.push({node,key,depth,open,branch,hiddenByOwner,unavailable,children});
      if (branch && open) visit(children, depth + 1, hiddenByOwner, outsideFrontier);
    }
  };
  visit(roots, 0, owner.hiddenByOwner, owner.outsideFrontier);
  return rows;
}
function findNodeLabel(nodes, selectionId) {
  for (const node of nodes || []) {
    if (node.selectionId === selectionId) return node.label;
    const found = findNodeLabel(node.children, selectionId);
    if (found) return found;
  }
  return '';
}

// The disclosure a row shows: a button, or — while Select's filter decides the tree's shape —
// the same chevron as a mark nobody can press.
function Disclosure({ node, open, locked, toggle }) {
  if (locked) return <span aria-hidden="true" data-disclosure-locked={open ? "open" : "shut"} className="grid h-6 w-3 shrink-0 place-items-center opacity-50"><TreeRowChevron expanded={open}/></span>;
  return <button type="button" aria-label={`${open ? 'Collapse' : 'Expand'} ${node.label}`} aria-expanded={open}
    className="grid h-6 w-3 shrink-0 place-items-center rounded focus-visible:ring-2 focus-visible:ring-ring"
    onClick={()=>toggle(node)}><TreeRowChevron expanded={open}/></button>;
}

// One row of the tree, the rows under it drawn after it by the list (`visibleRows`).
function ModelingRow({ node, depth, open, branch, locked, disabled, selected, joinAbove, joinBelow, hiddenByOwner, unavailable, actionsShown, actionsWidth, partControls, toggle, choose }) {
  const underActions = actionsWidth && (actionsShown ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover);
  return <XbfPartMenu node={node} controls={partControls} disabled={disabled}>
    <TreeRowSurface dense active={selected} className={cn('group/row relative gap-0 pr-0', hiddenByOwner && 'opacity-50')}
      onMouseEnter={() => partControls.onHoverTreeNode?.(node.selectionId || '')}
      onMouseLeave={() => partControls.onHoverTreeNode?.('')} style={{paddingLeft:TREE_ROW_INSET_PX+depth*TREE_INDENT_PX, ...joinedCorners(joinAbove, joinBelow), ...(actionsWidth && {'--row-actions':actionsWidth})}}>
      <TreeRowGuides depth={depth} inset={TREE_ROW_INSET_PX}/>
      {branch && <Disclosure node={node} open={open} locked={locked} toggle={toggle}/>}
      <TooltipHint content={node.label} overflowOnly><button type="button" aria-label={`Select ${node.label}`} aria-pressed={selected}
        disabled={disabled || unavailable || !(node.selectionId || node.memberSelectionIds?.length)}
        onClick={event=>{if(event.detail < 2)choose(node,event);}} onDoubleClick={event=>choose(node,event)}
        className={cn('flex h-full min-w-0 flex-1 items-center gap-1 rounded pr-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40', branch && 'pl-1', underActions)}>
        {!branch && <Box className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE}/>}
        <TreeRowLabel className="flex-1">{node.label}</TreeRowLabel>
      </button></TooltipHint>
      {node.selectionId && <XbfPartActions node={node} controls={partControls} disabled={disabled}/>}
    </TreeRowSurface>
  </XbfPartMenu>;
}

const MemoModelingRow = memo(ModelingRow);

// A search hit is the tree row without its place in the tree.
function ModelingSearchRow({ match, index, availability, selected, joinAbove, joinBelow, actionsShown, actionsWidth, cursor, choose, disabled, partControls }) {
  const {entry,indices}=match,{node}=entry;
  const Icon = icons[node.kind] || Box;
  const {hiddenByOwner,unavailable}=modelTreeSearchChain(index,match.at).reduce(
    (owner,step)=>nodeAvailability(step,availability,owner.hiddenByOwner,owner.outsideFrontier),{hiddenByOwner:false,outsideFrontier:false});
  const underActions = actionsWidth && (actionsShown ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover);
  return <XbfPartMenu node={node} controls={partControls} disabled={disabled}>
    <TreeRowSurface dense active={selected} cursor={cursor} className={cn('group/row relative gap-0 pr-0', hiddenByOwner && 'opacity-50')}
      onMouseEnter={() => partControls.onHoverTreeNode?.(node.selectionId || '')}
      onMouseLeave={() => partControls.onHoverTreeNode?.('')} style={{...joinedCorners(joinAbove, joinBelow), ...(actionsWidth && {'--row-actions':actionsWidth})}}>
      <TooltipHint content={`${entry.prefix}${node.label}`} overflowOnly><button type="button" aria-label={`Select ${node.label}`} aria-pressed={selected}
        disabled={disabled || unavailable || !node.selectionId}
        onClick={event=>{if(event.detail < 2)choose(node,event);}} onDoubleClick={event=>choose(node,event)}
        className={cn('flex h-full min-w-0 flex-1 items-center gap-1 rounded pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40', underActions)} style={{paddingLeft:TREE_ROW_INSET_PX}}>
        <Icon className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE}/>
        <TreeRowLabel className="max-w-full shrink-0"><TreeFilterHighlight indices={indices} text={entry.label}/></TreeRowLabel>
        {entry.prefix && <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{entry.prefix.slice(0,-1)}</TreeRowLabel>}
      </button></TooltipHint>
      {node.selectionId && <XbfPartActions node={node} controls={partControls} disabled={disabled}/>}
    </TreeRowSurface>
  </XbfPartMenu>;
}

const MemoModelingSearchRow = memo(ModelingSearchRow);

/**
 * The file sidebar's Model tree: the filter and the tree of an assembly's subassemblies and
 * parts, on screen while `active` and mounted otherwise. Its shape follows Select's `mode`: under
 * All it is the person's own; under Parts, Faces and Edges every assembly is open and the
 * disclosure locked.
 *
 * @param {{ tree: ReturnType<typeof import("./xbfTree.js").presentXbfTree>, active: boolean, disabled?: boolean,
 *   mode?: string, selectedIds: string[], onClearSelection: () => void, partControls: object }} props
 *   `selectedIds`: the parts and assemblies selected, and the faces and edges (revealed at their part).
 */
function XbfModelTree({ tree: presented, active, disabled, mode='all', selectedIds=EMPTY, onClearSelection, partControls=NO_CONTROLS }) {
  const [localExpanded,setLocalExpanded]=useState(()=>new Set());
  const rowHeight=useTreeRowHeight();
  const tree=presented.roots;
  const implicitRoots=useMemo(()=>implicitXbfRoots(tree),[tree]);
  const locked=mode !== 'all';
  // Every row that is open while the mode holds the disclosure: every assembly and folded group.
  const lockedExpansion=useMemo(()=>{
    if(!locked)return null;
    const ids=new Set();
    const visit=nodes=>{for(const node of nodes){if(node.kind === 'part')continue;ids.add(node.id);visit(node.children || EMPTY);}};
    visit(tree);
    return ids;
  },[locked,tree]);
  const foldedRows=useMemo(()=>{
    const rows=[];
    const visit=nodes=>{for(const node of nodes){
      if(node.memberSelectionIds?.length)rows.push(node);
      visit(node.children || EMPTY);
    }};
    visit(tree);
    return rows;
  },[tree]);
  const visibleRoots=implicitRoots.length ? implicitRoots.at(-1).children : tree;
  const availability=useMemo(()=>availabilityOf(partControls.hiddenPartIds,partControls.selectableNodeIds),[partControls.hiddenPartIds,partControls.selectableNodeIds]);
  const implicitOwner=useMemo(()=>implicitRoots.reduce((owner,node)=>nodeAvailability(node,availability,owner.hiddenByOwner,owner.outsideFrontier),{hiddenByOwner:false,outsideFrontier:false}),[implicitRoots,availability]);
  // The host's open rows: an assembly by its selection id, a folded group (which selects nothing) by
  // its row's own id, so the file's view keeps a group's expansion with the rest of the tree.
  const expanded=useMemo(()=>lockedExpansion
    ? new Set([...lockedExpansion,...implicitRoots.map(node=>node.id)])
    : new Set([...localExpanded,...implicitRoots.map(node=>node.id),
      ...(partControls.expandedTreeNodeIds || EMPTY).map(id=>(String(id).startsWith('model:') ? id : `model:${id}`))]),
  [lockedExpansion,localExpanded,implicitRoots,partControls.expandedTreeNodeIds]);
  // An implicit root (an assembly that is the tree's one choice) is open in the host as well, so
  // viewport picking reaches what the tree shows under it.
  const openedRoots=useRef(new Set());
  useEffect(()=>{
    if(!active || disabled || !partControls.onToggleTreeNode)return;
    let owner={hiddenByOwner:false,outsideFrontier:false};
    for(const node of implicitRoots){
      owner=nodeAvailability(node,availability,owner.hiddenByOwner,owner.outsideFrontier);
      if(openedRoots.current.has(node.id) || owner.hiddenByOwner)continue;
      if(!partControls.expandedTreeNodeIds?.includes(node.selectionId))partControls.onToggleTreeNode(node.selectionId);
      openedRoots.current.add(node.id);
    }
  },[active,disabled,implicitRoots,partControls.expandedTreeNodeIds,partControls.onToggleTreeNode,availability]);
  const rows=useMemo(()=>visibleRows(visibleRoots,expanded,availability,implicitOwner),[visibleRoots,expanded,availability,implicitOwner]);
  const rowIndex=useMemo(()=>{const index=new Map();rows.forEach((row,at)=>{if(!index.has(row.node.id))index.set(row.node.id,at);});return index;},[rows]);
  const rowElements=useRef(new Map());
  const registerRow=useCallback((key,element)=>{if(element)rowElements.current.set(key,element);else rowElements.current.delete(key);},[]);
  // Search is a second view of the same tree. Typing never touches expansion.
  const {query,searching,deferredQuery,index:searchIndex,found,cursorId,listRef,changeQuery,onKeyDown:onSearchKeyDown}=useTreeSearch(tree);
  const latest=useRef(null);
  latest.current={partControls};
  // A selected part or assembly at its row; a picked face or edge at its part's.
  const paths=useMemo(()=>xbfSelectionPaths(tree,selectedIds),[tree,selectedIds]);
  const revealKey=JSON.stringify(selectedIds);
  const reveal=useRef({key:null,complete:false});
  useEffect(()=>{
    if(reveal.current.key !== revealKey)reveal.current={key:revealKey,complete:false};
    if(!active || reveal.current.complete || !paths.length)return;
    const target=paths.at(-1).at(-1);
    const missing=paths.flatMap(path=>path.slice(0,-1)).filter(node=>!expanded.has(node.id));
    // A locked tree does not open for a pick: what the mode shows is what there is to scroll to.
    if(missing.length && locked){reveal.current.complete=true;return;}
    if(missing.length){
      const local=[];
      for(const node of new Map(missing.map(node=>[node.id,node])).values()){
        if(node.selectionId && partControls.onToggleTreeNode)partControls.onToggleTreeNode(node.selectionId);
        else local.push(node.id);
      }
      if(local.length)setLocalExpanded(current=>new Set([...current,...local]));
      return;
    }
    if(searching)return;
    const row=rowElements.current.get(target.id);
    if(row){revealRow(row);reveal.current.complete=true;}
  },[active,revealKey,paths,expanded,locked,partControls.onToggleTreeNode,searching]);

  // The rows' callbacks never change; each reads the tree as it is when pressed.
  const choose=useCallback((node,event)=>{
    const {partControls}=latest.current;
    if (event?.type === 'dblclick') {
      const components = node.memberSelectionIds?.length ? node.memberSelectionIds : node.selectionId;
      if (components && partControls.isAssemblyView) partControls.onFocusTreeNode?.(components);
      return;
    }
    // A folded row stands for every instance under it, so it selects them all.
    if(node.memberSelectionIds?.length){
      const additive=event?.shiftKey || event?.metaKey || event?.ctrlKey;
      node.memberSelectionIds.forEach((id,index)=>partControls.onSelectTreeNode?.(id,{multiSelect:additive || index > 0}));
      return;
    }
    if(node.selectionId)partControls.onSelectTreeNode?.(node.selectionId,{multiSelect:event?.shiftKey || event?.metaKey || event?.ctrlKey});
  },[]);
  const toggle=useCallback(node=>{
    const {partControls}=latest.current;
    if(partControls.onToggleTreeNode){partControls.onToggleTreeNode(node.selectionId || node.id);return;}
    setLocalExpanded(current=>{const next=new Set(current);if(next.has(node.id))next.delete(node.id);else next.add(node.id);return next;});
  },[]);
  const selectedNodeIds=useMemo(()=>selectedIds.filter(id=>!String(id).includes('/')),[selectedIds]);
  const highlighted=useMemo(()=>{
    const ids=new Set(paths.map(path=>path.at(-1).id));
    for(const node of foldedRows)if(node.memberSelectionIds.every(id=>selectedNodeIds.includes(id)))ids.add(node.id);
    return ids;
  },[paths,foldedRows,selectedNodeIds]);
  const isolatedLabels=useMemo(()=>(partControls.focusedNodeIds||EMPTY).map(id=>findNodeLabel(visibleRoots,id)||id),[partControls.focusedNodeIds,visibleRoots]);
  const revealIndex=paths.length ? rowIndex.get(paths.at(-1).at(-1).id) : undefined;
  const treePinned=useMemo(()=>revealIndex === undefined ? EMPTY : [revealIndex],[revealIndex]);
  const matches=found.matches;
  const cursorIndex=searching ? matches.findIndex(match=>match.entry.node.id === cursorId) : -1;
  const searchPinned=useMemo(()=>cursorIndex < 0 ? EMPTY : [cursorIndex],[cursorIndex]);
  const {isAssemblyView,hiddenPartIds,focusedNodeIds,onHoverTreeNode,onFocusTreeNode,onUnfocusTreeNode,onTogglePartVisibility,menuForNode,partMenuActions}=partControls;
  const rowControls=useMemo(()=>({isAssemblyView,hiddenPartIds,focusedNodeIds,onHoverTreeNode,onFocusTreeNode,onUnfocusTreeNode,onTogglePartVisibility,menuForNode,partMenuActions}),
    [isAssemblyView,hiddenPartIds,focusedNodeIds,onHoverTreeNode,onFocusTreeNode,onUnfocusTreeNode,onTogglePartVisibility,menuForNode,partMenuActions]);
  const actionsOf=node=>node.selectionId ? rowActionsLayout(node,partControls) : null;
  const renderTreeRow=at=>{
    const row=rows[at],on=highlighted.has(row.node.id),actions=actionsOf(row.node);
    return <MemoModelingRow node={row.node} depth={row.depth} open={row.open} branch={row.branch} disabled={disabled} locked={locked}
      actionsShown={Boolean(actions?.shown)} actionsWidth={actions?.width}
      selected={on} joinAbove={on && at > 0 && highlighted.has(rows[at-1].node.id)} joinBelow={on && at < rows.length-1 && highlighted.has(rows[at+1].node.id)}
      hiddenByOwner={row.hiddenByOwner} unavailable={row.unavailable} partControls={rowControls} toggle={toggle} choose={choose}/>;
  };
  const renderSearchRow=at=>{
    const match=matches[at],on=highlighted.has(match.entry.node.id),actions=actionsOf(match.entry.node);
    return <MemoModelingSearchRow match={match} index={searchIndex} availability={availability} cursor={match.entry.node.id === cursorId}
      actionsShown={Boolean(actions?.shown)} actionsWidth={actions?.width}
      selected={on} joinAbove={on && at > 0 && highlighted.has(matches[at-1].entry.node.id)} joinBelow={on && at < matches.length-1 && highlighted.has(matches[at+1].entry.node.id)}
      choose={choose} disabled={disabled} partControls={rowControls}/>;
  };
  // Headed by its filter, always there, then Show all while parts are hidden.
  return <ToolPanel id="tree" label="Model tree" fit="tree" resizable collapsible={false} hidden={!active}
    header={<TreeFilterInput label="Filter model" placeholder="Filter…" value={query} onChange={changeQuery} onKeyDown={onSearchKeyDown} dense
      className="px-0 shadow-none" trailing={<>
        {partControls.hiddenPartIds?.length > 0 && <Button disabled={disabled} type="button" variant="ghost" size="sm" className="h-5 shrink-0 px-1.5 text-tiny text-muted-foreground" onClick={partControls.showAllHiddenParts}>Show all</Button>}
      </>}/>}>
    <div className="flex flex-col text-tiny" aria-label="Modeling tree">
      <div ref={listRef} className="px-1 py-1" aria-label="Model tree area"
        onClick={event=>{if(!disabled && !event.target.closest('li,button,input,[role="menu"]'))onClearSelection?.();}}>
        {isolatedLabels.length > 0 && <div role="status" aria-label="Isolation" className="mb-1 flex min-h-7 items-center gap-2 rounded-md bg-accent/60 px-2 text-tiny">
          <Focus className="size-3 shrink-0 text-foreground" aria-hidden="true"/>
          <TooltipHint content={isolatedLabels.join(', ')} overflowOnly><span className="min-w-0 flex-1 truncate">Isolated: {isolatedLabels.join(', ')}</span></TooltipHint>
          <Button disabled={disabled} type="button" variant="ghost" size="sm" className="h-6 shrink-0 px-1.5 text-tiny" onClick={partControls.onExitAllIsolate}>Exit</Button>
        </div>}
        {searching && <p role="status" className="px-2 py-1 text-micro text-muted-foreground">{found.total > found.matches.length ? `First ${found.matches.length} of ${found.total.toLocaleString()} matches` : `${found.total} ${found.total === 1 ? 'match' : 'matches'}`}</p>}
        {searching ? found.matches.length
          ? <VirtualRows key="search" aria-label="Model search results" count={matches.length} rowHeight={rowHeight} pinned={searchPinned}
            rowKey={at=>matches[at].entry.node.id} rowProps={at=>({className:'min-w-0','data-search-row':matches[at].entry.node.id})} renderRow={renderSearchRow}/>
          : deferredQuery.trim() && <p className="px-3 py-6 text-center text-tiny text-muted-foreground">{`No part matches “${deferredQuery.trim()}”`}</p>
        : <VirtualRows key="tree" aria-label="Model" count={rows.length} rowHeight={rowHeight} pinned={treePinned}
          rowKey={at=>rows[at].key} rowProps={at=>({className:'min-w-0','aria-level':rows[at].depth+1,'data-tree-part':rows[at].node.kind === 'part' ? rows[at].node.id : undefined})}
          renderRow={renderTreeRow} registerRow={registerRow}/>}
      </div>
    </div>
  </ToolPanel>;
}

export default memo(XbfModelTree);
