import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Box, Boxes, Circle, CornerUpRight, Focus, Layers, RotateCw, Shapes, Spline, SquareDashed } from 'lucide-react';
import { Button } from '@text-to-cad/ui/primitives/button';
import { TREE_ROW_DENSE_HEIGHT, TREE_ROW_DENSE_ICON_CLASS, TreeRowSurface, TreeRowChevron, TreeRowLabel } from '@text-to-cad/ui/primitives/tree-row';
import { TreeFilterHighlight, TreeFilterInput } from '@text-to-cad/ui/primitives/tree-filter';
import { cn } from '@text-to-cad/ui/utils';
import ModelPartMenu, { FeatureReferencesContext } from './ModelPartMenu.jsx';
import ModelPartActions, { ROW_NAME_UNDER_ACTIONS, rowActionsLayout } from './ModelPartActions.jsx';
import { modelingSelectionPaths } from '../../workbench/modelingSelection.js';
import ToolPanel, { ToolPanelCollapse, ToolPanelFooterButton } from '../../../kit/tools/ToolPanel.jsx';
import { TOOL_PANEL_REFERENCE_HEIGHT } from '../../../kit/tools/toolStackLayout.js';
import { useViewerMobile } from '../../../../file-viewer/responsive.js';
import { modelingReferenceIds } from '../../workbench/modelingTree.js';
import { implicitModelingRoots, presentModelingAssembly } from '../../workbench/modelingPresentation.js';
import { modelTreeSearchChain, useTreeSearch } from '../../../kit/inspector/modelTreeSearch.js';
import VirtualRows from '../../../kit/inspector/VirtualRows.jsx';

const EMPTY = [];
const NO_CONTROLS = {};
/**
 * Above this many rows — the fully expanded tree's assemblies and parts, not the features
 * recognition adds under a part later, so the tree never changes shape under the person — Faces
 * and Edges open a tree with its parts closed instead of
 * opening every part. Each part opens by its own disclosure, a pick inside it, or the menu.
 */
export const LARGE_TREE_ROWS = 300;
/** How long the pointer rests on a part in the viewport before its topology is asked for. */
export const TOPOLOGY_DWELL_MS = 150;
const icons = {part:Box,assembly:Boxes,group:Boxes,boss:Layers,pocket:Shapes,hole:Circle,body:Box,extrude:Layers,loft:Layers,cut:Shapes,revolve:RotateCw,round:CornerUpRight,profile:SquareDashed,curve:Spline,remainder:Box};
const number = n => n.toLocaleString(undefined,{maximumFractionDigits:3});

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
// level deeper. Curves are never rows. A row carries what it inherits from its owners.
function visibleRows(roots, expanded, availability, owner) {
  const rows = [], keys = new Set();
  const visit = (nodes, depth, inheritedHidden, inheritedUnavailable) => {
    for (const node of nodes) {
      const children = (node.children || EMPTY).filter(child => child.kind !== 'curve');
      const open = expanded.has(node.id);
      const branch = children.length > 0 || Boolean(node.recognitionPending);
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

// The disclosure a row shows: a button, or — while the Select mode decides the tree's shape
// (`TREE_SHAPES`) — the same chevron as a mark nobody can press.
function Disclosure({ node, open, locked, toggle }) {
  if (locked) return <span aria-hidden="true" data-disclosure-locked={open ? "open" : "shut"} className="grid h-6 w-4 shrink-0 place-items-center opacity-50"><TreeRowChevron expanded={open} dense/></span>;
  return <button type="button" aria-label={`${open ? 'Collapse' : 'Expand'} ${node.label}`} aria-expanded={open}
    className="grid h-6 w-4 shrink-0 place-items-center rounded focus-visible:ring-2 focus-visible:ring-ring"
    onClick={()=>toggle(node)}><TreeRowChevron expanded={open} dense/></button>;
}

// One row of the tree, the rows under it drawn after it by the list (`visibleRows`). Its props
// are the row's own facts — its selection and joins as booleans, callbacks that never change —
// so a tree re-rendered for anything else leaves it alone.
function ModelingRow({ node, depth, open, branch, locked, disabled, selected, joinAbove, joinBelow, hiddenByOwner, unavailable, actionsShown, actionsWidth, partControls, feature, toggle, choose }) {
  const Icon = icons[node.kind] || Box;
  // An assembly outside the isolate/picking frontier cannot select itself, but
  // its descendants can. Only a hidden owner blocks its entire subtree.
  // The name fades out under its actions (`ROW_NAME_UNDER_ACTIONS`): always while one is on
  // (`actionsShown`), otherwise on hover. `actionsWidth` is the room they take.
  const underActions = actionsWidth && (actionsShown ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover);
  return <ModelPartMenu node={node} controls={partControls} feature={feature} disabled={disabled}>
    <TreeRowSurface dense active={selected} className={cn('group/row relative gap-0 pr-0', hiddenByOwner && 'opacity-50')}
      onMouseEnter={() => partControls.onHoverTreeNode?.(node.selectionId || node.occurrenceId || '')}
      onMouseLeave={() => partControls.onHoverTreeNode?.('')} style={{paddingLeft:depth*12, ...joinedCorners(joinAbove, joinBelow), ...(actionsWidth && {'--row-actions':actionsWidth})}}>
      {branch ? <Disclosure node={node} open={open} locked={locked} toggle={toggle}/> : <span className="w-4 shrink-0"/>}
      <TooltipHint content={node.label} overflowOnly><button type="button" aria-label={`Select ${node.label}`} aria-pressed={selected}
        disabled={disabled || unavailable || !(node.selectionId || node.memberSelectionIds?.length || node.faces?.length || node.edges?.length)}
        onClick={event=>{if(event.detail < 2)choose(node,event);}} onDoubleClick={event=>choose(node,event)}
        className={cn('flex h-full min-w-0 flex-1 items-center gap-1 rounded pr-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40', underActions)}>
        <Icon className={TREE_ROW_DENSE_ICON_CLASS}/><TreeRowLabel className="flex-1">{node.label}</TreeRowLabel>
      </button></TooltipHint>
      {node.selectionId && <ModelPartActions node={node} controls={partControls} disabled={disabled}/>}
    </TreeRowSurface>
  </ModelPartMenu>;
}

// Named so a profiler (and the render counts in the specs) can tell the rows apart.
const MemoModelingRow = memo(ModelingRow);

// A search hit is the tree row without its place in the tree: the same menu, eye
// and availability, with the owners it would sit under named instead of drawn.
function ModelingSearchRow({ match, index, availability, selected, joinAbove, joinBelow, actionsShown, actionsWidth, cursor, choose, disabled, partControls, feature }) {
  const {entry,indices}=match,{node}=entry;
  const Icon = icons[node.kind] || Box;
  const {hiddenByOwner,unavailable}=modelTreeSearchChain(index,match.at).reduce(
    (owner,step)=>nodeAvailability(step,availability,owner.hiddenByOwner,owner.outsideFrontier),{hiddenByOwner:false,outsideFrontier:false});
  const underActions = actionsWidth && (actionsShown ? ROW_NAME_UNDER_ACTIONS.shown : ROW_NAME_UNDER_ACTIONS.hover);
  return <ModelPartMenu node={node} controls={partControls} feature={feature} disabled={disabled}>
    <TreeRowSurface dense active={selected} cursor={cursor} className={cn('group/row relative gap-0 pr-0', hiddenByOwner && 'opacity-50')}
      onMouseEnter={() => partControls.onHoverTreeNode?.(node.selectionId || node.occurrenceId || '')}
      onMouseLeave={() => partControls.onHoverTreeNode?.('')} style={{...joinedCorners(joinAbove, joinBelow), ...(actionsWidth && {'--row-actions':actionsWidth})}}>
      <TooltipHint content={`${entry.prefix}${node.label}`} overflowOnly><button type="button" aria-label={`Select ${node.label}`} aria-pressed={selected}
        disabled={disabled || unavailable || !(node.selectionId || node.faces?.length || node.edges?.length)}
        onClick={event=>{if(event.detail < 2)choose(node,event);}} onDoubleClick={event=>choose(node,event)}
        className={cn('flex h-full min-w-0 flex-1 items-center gap-1.5 rounded pl-2 pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40', underActions)}>
        <Icon className={TREE_ROW_DENSE_ICON_CLASS}/>
        {/* Name first: in a narrow panel a deep owner path takes the truncation, never the name. */}
        <TreeRowLabel className="max-w-full shrink-0"><TreeFilterHighlight indices={indices} text={entry.label}/></TreeRowLabel>
        {entry.prefix && <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{entry.prefix.slice(0,-1)}</TreeRowLabel>}
      </button></TooltipHint>
      {node.selectionId && <ModelPartActions node={node} controls={partControls} disabled={disabled}/>}
    </TreeRowSurface>
  </ModelPartMenu>;
}

const MemoModelingSearchRow = memo(ModelingSearchRow);

/**
 * Read-only geometry inference; assembly instances share recognition, never selection IDs.
 *
 * Two panels of the tool stack: **Features** (the filter and the tree) and, while something is
 * picked, its **Reference**. Both are on screen while `active` — the Select tool is up — and
 * stay mounted otherwise.
 *
 * The tree's shape follows the Select tool's `mode`. Under All it is the person's own. Under
 * Parts every assembly is open and every part shut, so each part is a row and none opens onto
 * its faces; under Faces and Edges everything is open, down to the features whose faces and
 * edges are picked. Outside All the disclosure is locked. A part's topology is asked for as its
 * row comes on screen, never for a whole large assembly at once.
 */
function ModelingTree({ modeling, active, disabled, mode='all', modeMenu=null, loading=false, references=EMPTY, selectedReferenceIds=EMPTY, selectedPartIds=EMPTY, onLoadTopology, onRequestRecognition, onSelect, onClearSelection, stepRoot, selectedReferences, selectionDetails, selectionCopy=null, activeTreeNodeScrollKey, partControls=NO_CONTROLS, hoverStore=null }) {
  const mobile = useViewerMobile();
  const {descriptor,results,error,retryFailed}=modeling;
  const [selected,setSelected]=useState(null),[pending,setPending]=useState(null),[localExpanded,setLocalExpanded]=useState(new Set());
  const tree=useMemo(()=>presentModelingAssembly(descriptor,results,stepRoot),[descriptor,results,stepRoot]);
  const implicitRoots=useMemo(()=>implicitModelingRoots(tree),[tree]);
  const locked=mode !== 'all',topologyMode=mode === 'faces' || mode === 'edges';
  // Every row that is open while the mode holds the disclosure: under Parts, all but the parts.
  const lockedExpansion=useMemo(()=>{
    if(!locked)return null;
    const ids=new Set();
    const visit=nodes=>{for(const node of nodes){
      if(!topologyMode && node.kind === 'part')continue;
      ids.add(node.id);visit(node.children || EMPTY);
    }};
    visit(tree);
    return ids;
  },[locked,topologyMode,tree]);
  const partNodes=useMemo(()=>{
    const parts=new Map();
    const visit=nodes=>{for(const node of nodes){if(node.kind === 'part')parts.set(node.id,node);visit(node.children || EMPTY);}};
    visit(tree);
    return parts;
  },[tree]);
  // Under Faces or Edges, the parts whose rows have been on screen: only those ask for topology.
  const [seenParts,setSeenParts]=useState(()=>new Set());
  const loadedParts=useRef(new Set());
  useEffect(()=>{if(!topologyMode){loadedParts.current=new Set();setSeenParts(current=>current.size ? new Set() : current);}},[topologyMode]);
  const foldedRows=useMemo(()=>{
    const rows=[];
    const visit=nodes=>{for(const node of nodes){
      if(node.memberSelectionIds?.length)rows.push(node);
      visit(node.children || EMPTY);
    }};
    visit(tree);
    return rows;
  },[tree]);
  const visibleRoots=implicitRoots.length ? implicitRoots.at(-1).children || EMPTY : tree;
  const availability=useMemo(()=>availabilityOf(partControls.hiddenPartIds,partControls.selectableNodeIds),[partControls.hiddenPartIds,partControls.selectableNodeIds]);
  const implicitOwner=useMemo(()=>implicitRoots.reduce((owner,node)=>nodeAvailability(node,availability,owner.hiddenByOwner,owner.outsideFrontier),{hiddenByOwner:false,outsideFrontier:false}),[implicitRoots,availability]);
  const componentIds=useMemo(()=>[...new Set(descriptor?.occurrences.map(o=>o.component)||[])],[descriptor]);
  // A large tree under Faces or Edges (`LARGE_TREE_ROWS`): its parts start closed and open one by
  // one, each by its own disclosure; the mode still holds every assembly open.
  const structuralRows=useMemo(()=>{
    let count=0;
    const visit=nodes=>{for(const node of nodes){if(node.kind === 'curve')continue;count+=1;if(node.kind !== 'part')visit(node.children || EMPTY);}};
    visit(visibleRoots);
    return count;
  },[visibleRoots]);
  const largeTopology=topologyMode && structuralRows > LARGE_TREE_ROWS;
  const [openParts,setOpenParts]=useState(()=>new Set());
  // Opening a part (its disclosure, its Expand, a pick inside it) asks for its topology and
  // recognition at once, on screen or not; Expand all leaves that to the rows as they show.
  const seeParts=useCallback(ids=>setSeenParts(current=>ids.every(id=>current.has(id)) ? current : new Set([...current,...ids])),[]);
  useEffect(()=>{if(!topologyMode)setOpenParts(current=>current.size ? new Set() : current);},[topologyMode]);
  const expanded=useMemo(()=>{
    if(lockedExpansion){
      const ids=new Set(lockedExpansion);
      if(largeTopology)for(const id of partNodes.keys())if(!openParts.has(id))ids.delete(id);
      for(const node of implicitRoots)ids.add(node.id);
      return ids;
    }
    return new Set([...localExpanded,...implicitRoots.map(node=>node.id),...(partControls.expandedTreeNodeIds || EMPTY).map(id=>`model:${id}`)]);
  },[lockedExpansion,largeTopology,partNodes,openParts,localExpanded,implicitRoots,partControls.expandedTreeNodeIds]);
  const openedRoots=useRef(new Set());
  useEffect(()=>{
    if(!active || disabled)return;
    let owner={hiddenByOwner:false,outsideFrontier:false};
    for(const node of implicitRoots){
      owner=nodeAvailability(node,availability,owner.hiddenByOwner,owner.outsideFrontier);
      const key=node.occurrenceId ? `occurrence:${node.occurrenceId}` : node.id;
      if(openedRoots.current.has(key) || owner.hiddenByOwner || (node.occurrenceId && owner.unavailable))continue;
      // Loading a part also expands its canonical owner in the host. That keeps
      // viewport picking and lazy topology aligned with the flattened tree.
      if(node.occurrenceId && onLoadTopology){
        onLoadTopology([node.occurrenceId]);openedRoots.current.add(key);
      } else if(node.selectionId && partControls.onToggleTreeNode){
        if(!partControls.expandedTreeNodeIds?.includes(node.selectionId))partControls.onToggleTreeNode(node.selectionId);
        openedRoots.current.add(key);
      }
    }
  },[active,disabled,implicitRoots,onLoadTopology,partControls.expandedTreeNodeIds,partControls.onToggleTreeNode,availability]);
  // The tree as the rows the list draws: what is open, under the Select mode's lock or the person's.
  const rows=useMemo(()=>visibleRows(visibleRoots,expanded,availability,implicitOwner),[visibleRoots,expanded,availability,implicitOwner]);
  const rowIndex=useMemo(()=>{const index=new Map();rows.forEach((row,at)=>{if(!index.has(row.node.id))index.set(row.node.id,at);});return index;},[rows]);
  // The mounted rows, by key: the reveal scrolls the selection's row, which the list keeps mounted.
  const rowElements=useRef(new Map());
  const registerRow=useCallback((key,element)=>{if(element)rowElements.current.set(key,element);else rowElements.current.delete(key);},[]);
  // Search is a second view of the same tree. Typing never touches expansion,
  // which is also the picking frontier and the topology request; the rows
  // unmount so a large open tree is not re-rendered per keystroke.
  const {query,searching,deferredQuery,index:searchIndex,found,cursorId,listRef,changeQuery,onKeyDown:onSearchKeyDown}=useTreeSearch(tree);
  // Under Faces or Edges, the part rows the list has on screen (never its margin) are seen, and
  // only those ask for topology and recognition. The tree's list is not drawn during a search.
  // In a large tree a closed part is not seen for being on screen: opening it is what asks.
  const onVisibleRows=useMemo(()=>topologyMode && active && !disabled ? (first,last)=>{
    const ids=[];
    for(let at=first;at<=last;at+=1){const row=rows[at];if(row?.node.kind === 'part' && (!largeTopology || row.open))ids.push(row.node.id);}
    if(ids.length)setSeenParts(current=>ids.every(id=>current.has(id)) ? current : new Set([...current,...ids]));
  } : null,[topologyMode,active,disabled,rows,largeTopology]);
  useEffect(()=>{
    if(!topologyMode || !active || disabled || !onLoadTopology)return;
    const ids=[...seenParts].filter(id=>!loadedParts.current.has(id));
    for(const id of ids)loadedParts.current.add(id);
    const partIds=ids.map(id=>partNodes.get(id)).map(node=>node?.selectionId || node?.occurrenceId).filter(Boolean);
    if(partIds.length)onLoadTopology(partIds);
  },[topologyMode,active,disabled,seenParts,partNodes,onLoadTopology]);
  const picked=useMemo(()=>selectedReferences || references.filter(ref=>selectedReferenceIds.includes(ref.id)),[selectedReferences,references,selectedReferenceIds]);
  const ids=selected ? modelingReferenceIds(selected,selected.occurrenceId,references) : EMPTY;
  const selection=new Set(selectedReferenceIds),showDetails=selected && (pending || (ids.length > 0 && ids.length === selection.size && ids.every(id=>selection.has(id))));
  const paths=useMemo(()=>{
    if(showDetails){
      const find=(nodes,parents=[])=>{for(const node of nodes){const path=[...parents,node];if(node.id === selected.id)return path;const child=find(node.children || EMPTY,path);if(child)return child;}return null;};
      const path=find(tree);
      if(path)return [path];
    }
    if(picked.length){
      const selectedIds=new Set(picked.map(ref=>ref.id));
      // Viewport All-mode selection returns the visible feature's canonical
      // bundle too. Preserve that row instead of expanding a matching group
      // into the individual feature paths represented by the same faces.
      const findVisible=(nodes,parents=[])=>{for(const node of nodes){
        if(node.kind === 'curve')continue;
        const path=[...parents,node];
        if(expanded.has(node.id)){const child=findVisible(node.children || EMPTY,path);if(child)return child;}
        if(!node.selectionId){
          const ids=modelingReferenceIds(node,node.occurrenceId,references);
          if(ids.length === selectedIds.size && ids.every(id=>selectedIds.has(id)))return path;
        }
      }return null;};
      const path=findVisible(tree);
      if(path)return [path];
    }
    return modelingSelectionPaths(tree,picked,selectedPartIds,descriptor,results);
  },[tree,picked,selectedPartIds,descriptor,results,showDetails,selected,expanded,references]);
  const selectionKey=JSON.stringify([selectedReferenceIds,selectedPartIds]);
  const revealKey=JSON.stringify([selectionKey,picked.map(ref=>ref.id),activeTreeNodeScrollKey]);
  const reveal=useRef({key:null,complete:false});
  useEffect(()=>{
    if(reveal.current.key !== revealKey)reveal.current={key:revealKey,complete:false};
    if(!active || reveal.current.complete || !paths.length)return;
    const target=paths.at(-1).at(-1);
    // A precise reference may arrive before recognition. Open its owner to
    // discover that row; selecting the part itself never opens its topology.
    const waitingForFeature=target.kind === 'part' && target.recognitionPending && picked.some(ref=>ref.occurrenceId === target.occurrenceId && ['face','edge'].includes(ref.selectorType));
    const ancestors=paths.flatMap(path=>path.slice(0,-1));
    if(waitingForFeature)ancestors.push(target);
    const missing=ancestors.filter(node=>!expanded.has(node.id));
    // A locked tree does not open for a pick: what the mode shows is what there is to scroll to.
    // In a large tree under Faces or Edges a closed part is the one thing that opens for it.
    if(missing.length && locked){
      if(largeTopology && missing.every(node=>node.kind === 'part' && partNodes.has(node.id))){
        setOpenParts(current=>missing.every(node=>current.has(node.id)) ? current : new Set([...current,...missing.map(node=>node.id)]));
        seeParts(missing.map(node=>node.id));
        return;
      }
      reveal.current.complete=true;return;
    }
    if(missing.length){
      const local=[];
      for(const node of new Map(missing.map(node=>[node.id,node])).values()){
        if(node.selectionId && partControls.onToggleTreeNode)partControls.onToggleTreeNode(node.selectionId);
        else local.push(node.id);
      }
      if(local.length)setLocalExpanded(current=>new Set([...current,...local]));
      return;
    }
    // A face or edge picked on a part not yet recognized waits for its feature row, so it asks for
    // that part's recognition itself: under Faces or Edges only parts seen on screen are asked
    // for, and a pick far down the tree is not one of them.
    if(waitingForFeature)seeParts([target.id]);
    // A search hit's owners open at once, so the selection is always a row the
    // tree holds; the one scroll waits for the tree to be back on screen.
    if(waitingForFeature || searching)return;
    const row=rowElements.current.get(target.id);
    if(row){row.scrollIntoView?.({block:'nearest'});reveal.current.complete=true;}
  },[active,revealKey,paths,expanded,locked,largeTopology,partNodes,seeParts,picked,partControls.onToggleTreeNode,searching]);

  const requestedOccurrences=useMemo(()=>{
    if(!active || disabled)return EMPTY;
    const requested=[];
    const visit=(nodes,inheritedHidden=false,inheritedUnavailable=false)=>{for(const node of nodes){
      if(!expanded.has(node.id))continue;
      const {hiddenByOwner,outsideFrontier,unavailable}=nodeAvailability(node,availability,inheritedHidden,inheritedUnavailable);
      if(node.kind === 'part' && node.occurrenceId && !unavailable && (!topologyMode || seenParts.has(node.id)))requested.push(node.occurrenceId);
      visit(node.children || EMPTY,hiddenByOwner,outsideFrontier);
    }};
    visit(tree);
    return [...new Set(requested)].sort();
  },[active,disabled,tree,expanded,topologyMode,seenParts,availability]);
  const requestKey=JSON.stringify(requestedOccurrences);
  useEffect(()=>{onRequestRecognition?.(JSON.parse(requestKey));},[requestKey,onRequestRecognition]);

  const {done,failed}=useMemo(()=>({done:componentIds.filter(id=>results[id]).length,failed:componentIds.filter(id=>results[id]?.error).length}),[componentIds,results]);
  useEffect(()=>{if(!active || disabled)setPending(null);},[active,disabled]);
  useEffect(()=>{
    if(!pending || !active || disabled)return;
    if(pending.selectionKey !== selectionKey){setPending(null);return;}
    const ids=modelingReferenceIds(pending,pending.occurrenceId,references);
    if(ids.length){onSelect?.(ids);setPending(null);}
  },[pending,active,disabled,references,onSelect,selectionKey]);
  const latest=useRef(null);
  latest.current={references,partControls,selectionKey,onSelect,onLoadTopology,largeTopology,openParts,partNodes};
  // The rows' callbacks never change; each reads the tree as it is when pressed.
  const choose=useCallback((node,event)=>{
    const {references,partControls,selectionKey,onSelect,onLoadTopology}=latest.current;
    if (event?.type === 'dblclick') {
      const components = node.memberSelectionIds?.length ? node.memberSelectionIds : node.selectionId;
      if (components) {
        if (partControls.isAssemblyView) partControls.onFocusTreeNode?.(components);
      } else if (modelingReferenceIds(node,node.occurrenceId,references).length) partControls.onCopySelection?.();
      return;
    }
    // A folded row stands for every instance under it, so it selects them all --
    // the alternative is a row that reads "(6)" and selects one of the six.
    if(node.memberSelectionIds?.length){
      setSelected(null);setPending(null);
      const additive=event?.shiftKey || event?.metaKey || event?.ctrlKey;
      node.memberSelectionIds.forEach((id,index)=>partControls.onSelectTreeNode?.(id,{multiSelect:additive || index > 0}));
      return;
    }
    if(node.selectionId){
      setSelected(null);setPending(null);
      partControls.onSelectTreeNode?.(node.selectionId,{multiSelect:event?.shiftKey || event?.metaKey || event?.ctrlKey});
      return;
    }
    setSelected(node);setPending(null);
    const ids=modelingReferenceIds(node,node.occurrenceId,references);
    if(ids.length)onSelect?.(ids);
    else if(node.faces?.length || node.edges?.length){setPending({...node,selectionKey});onLoadTopology?.([node.occurrenceId]);}
  },[]);
  const toggle=useCallback(node=>{
    const {partControls,largeTopology}=latest.current;
    if(largeTopology && node.kind === 'part'){
      if(!latest.current.openParts.has(node.id))seeParts([node.id]);
      setOpenParts(current=>{const next=new Set(current);if(next.has(node.id))next.delete(node.id);else next.add(node.id);return next;});
      return;
    }
    if(node.selectionId && partControls.onToggleTreeNode){partControls.onToggleTreeNode(node.selectionId);return;}
    setLocalExpanded(current=>{const next=new Set(current);if(next.has(node.id))next.delete(node.id);else next.add(node.id);return next;});
  },[seeParts]);
  const clearSelection=()=>{setSelected(null);setPending(null);onClearSelection?.();};
  // What a feature row's menu needs of the tree: the row's faces as reference ids, how to load
  // them, and the row's own click, so its Select is the click rather than a second opinion.
  // One object for the life of the tree: it reads the references as they are when a menu asks,
  // and the open menu follows them through `FeatureReferencesContext`, so loading faces re-renders
  // no row.
  const feature=useMemo(()=>({referenceIds:node=>modelingReferenceIds(node,node.occurrenceId,latest.current.references),
    loadTopology:ids=>latest.current.onLoadTopology?.(ids),choose}),[choose]);
  const highlighted=useMemo(()=>{
    const ids=new Set(showDetails ? [selected.id] : paths.map(path=>path.at(-1).id));
    // Its members are not rendered while it is collapsed, so the row itself carries
    // their selection; anything less and selecting a folded row looks like a no-op.
    for(const node of foldedRows)if(node.memberSelectionIds.every(id=>selectedPartIds.includes(id)))ids.add(node.id);
    return ids;
  },[showDetails,selected,paths,foldedRows,selectedPartIds]);
  const isolatedLabels=useMemo(()=>(partControls.focusedNodeIds||EMPTY).map(id=>findNodeLabel(visibleRoots,id)||id),[partControls.focusedNodeIds,visibleRoots]);
  // The list draws the rows in view; the selection's row and the search cursor stay mounted.
  const revealIndex=paths.length ? rowIndex.get(paths.at(-1).at(-1).id) : undefined;
  const treePinned=useMemo(()=>revealIndex === undefined ? EMPTY : [revealIndex],[revealIndex]);
  const matches=found.matches;
  const cursorIndex=searching ? matches.findIndex(match=>match.entry.node.id === cursorId) : -1;
  const searchPinned=useMemo(()=>cursorIndex < 0 ? EMPTY : [cursorIndex],[cursorIndex]);
  // What a row reads of the host's controls (its menu, its actions, its hover), and nothing else:
  // expanding the tree, which the host does as parts load, re-renders no row for it.
  const {isAssemblyView,hiddenPartIds,focusedNodeIds,onHoverTreeNode,onFocusTreeNode,onUnfocusTreeNode,onTogglePartVisibility,menuForNode,menuForReferences,partMenuActions}=partControls;
  // In a large tree under Faces or Edges, the viewport asks for a part's topology when the pointer
  // rests on it (`TOPOLOGY_DWELL_MS`) or presses it: hover is read from the viewport's store,
  // never React state, and each part is asked for once.
  const treeRef=useRef(null),dwelled=useRef(new Set());
  useEffect(()=>{if(!topologyMode)dwelled.current=new Set();},[topologyMode]);
  useEffect(()=>{
    if(!largeTopology || !active || disabled || !hoverStore)return undefined;
    const request=id=>{if(!id || dwelled.current.has(id))return;dwelled.current.add(id);latest.current.onLoadTopology?.([id]);};
    let timer=null,resting='';
    const follow=()=>{
      const id=hoverStore.getSnapshot().modelPartId || '';
      if(id === resting)return;
      resting=id;clearTimeout(timer);timer=null;
      if(id)timer=setTimeout(()=>request(id),TOPOLOGY_DWELL_MS);
    };
    const unsubscribe=hoverStore.subscribe(follow);
    follow();
    const surface=treeRef.current?.closest('[data-cad-surface]');
    const press=event=>{if(event.target instanceof Element && event.target.closest('canvas'))request(hoverStore.getSnapshot().modelPartId);};
    surface?.addEventListener('pointerdown',press,true);
    return ()=>{unsubscribe();clearTimeout(timer);surface?.removeEventListener('pointerdown',press,true);};
  },[largeTopology,active,disabled,hoverStore]);
  // In a large tree under Faces or Edges the menu's Expand and Collapse (a part row's) and Expand
  // all and Collapse all (every row's) open and close the parts, read as they are when it opens.
  const partBySelection=useMemo(()=>new Map([...partNodes.values()].filter(node=>node.selectionId).map(node=>[node.selectionId,node.id])),[partNodes]);
  const rowControls=useMemo(()=>{
    const controls={isAssemblyView,hiddenPartIds,focusedNodeIds,onHoverTreeNode,onFocusTreeNode,onUnfocusTreeNode,onTogglePartVisibility,menuForNode,menuForReferences,partMenuActions};
    if(!largeTopology)return controls;
    const setPart=(selectionId,open)=>{const id=partBySelection.get(selectionId);if(id && open)seeParts([id]);if(id)setOpenParts(current=>current.has(id) === open ? current : (next=>{if(open)next.add(id);else next.delete(id);return next;})(new Set(current)));};
    return {...controls,
      menuForNode:menuForNode && (id=>{
        const menu=menuForNode(id);
        if(!menu)return menu;
        const {openParts,partNodes}=latest.current,part=partBySelection.get(id);
        return {...menu,showExpandCollapse:true,expandSelectedDisabled:!part || openParts.has(part),collapseSelectedDisabled:!part || !openParts.has(part),
          expandAllDisabled:openParts.size >= partNodes.size,collapseAllDisabled:openParts.size === 0};
      }),
      partMenuActions:{...partMenuActions,
        onExpandSelected:menu=>setPart(menu?.nodeId,true),onCollapseSelected:menu=>setPart(menu?.nodeId,false),
        onExpandAll:()=>setOpenParts(new Set(latest.current.partNodes.keys())),onCollapseAll:()=>setOpenParts(current=>current.size ? new Set() : current)}};
  },[isAssemblyView,hiddenPartIds,focusedNodeIds,onHoverTreeNode,onFocusTreeNode,onUnfocusTreeNode,onTogglePartVisibility,menuForNode,menuForReferences,partMenuActions,largeTopology,partBySelection,seeParts]);
  // A row's actions as primitives (`rowActionsLayout`): whether one is on, and the room they take.
  const actionsOf=node=>node.selectionId ? rowActionsLayout(node,partControls) : null;
  const renderTreeRow=at=>{
    const row=rows[at],on=highlighted.has(row.node.id),actions=actionsOf(row.node);
    return <MemoModelingRow node={row.node} depth={row.depth} open={row.open} branch={row.branch} disabled={disabled}
      locked={locked && !(largeTopology && row.node.kind === 'part')}
      actionsShown={Boolean(actions?.shown)} actionsWidth={actions?.width}
      selected={on} joinAbove={on && at > 0 && highlighted.has(rows[at-1].node.id)} joinBelow={on && at < rows.length-1 && highlighted.has(rows[at+1].node.id)}
      hiddenByOwner={row.hiddenByOwner} unavailable={row.unavailable} partControls={rowControls}
      feature={row.node.selectionId ? null : feature} toggle={toggle} choose={choose}/>;
  };
  const renderSearchRow=at=>{
    const match=matches[at],on=highlighted.has(match.entry.node.id),actions=actionsOf(match.entry.node);
    return <MemoModelingSearchRow match={match} index={searchIndex} availability={availability} cursor={match.entry.node.id === cursorId}
      actionsShown={Boolean(actions?.shown)} actionsWidth={actions?.width}
      selected={on} joinAbove={on && at > 0 && highlighted.has(matches[at-1].entry.node.id)} joinBelow={on && at < matches.length-1 && highlighted.has(matches[at+1].entry.node.id)}
      choose={choose} disabled={disabled} partControls={rowControls} feature={match.entry.node.selectionId ? null : feature}/>;
  };
  const selectedNode=showDetails ? selected : paths.length === 1 ? paths[0].at(-1) : null;
  const nodeDetails=selectedNode && (selectedNode.summary || selectedNode.note || selectedNode.measurements?.length);
  // The Reference panel's heading is the reference being read (`useStepReference`: its name and
  // id, or the picker over several); a feature row picked in the tree heads it by its label until
  // its faces are what is selected.
  const referenceTitle=selectionDetails?.title ?? (selectedNode ? <span className="block truncate">{selectedNode.label}</span> : null);
  const details=showDetails && selected.edges?.length === 1 && !pending && selectionDetails ? selectionDetails.content : <>
    {nodeDetails && (showDetails || !selectionDetails) && <div className="mb-1 space-y-0.5 text-tiny" aria-label="Feature details">
      {showDetails && selectionDetails && <p>{selectedNode.label}</p>}
      {selectedNode.summary && <p className="text-muted-foreground">{selectedNode.summary}</p>}
      {selectedNode.note && <p className="text-muted-foreground">{selectedNode.note}</p>}
      {!!selectedNode.measurements?.length && <dl>{selectedNode.measurements.map(([label,value,unit])=><div key={label} className="grid grid-cols-[4rem_minmax(0,1fr)] gap-2 py-0.5"><dt className="text-muted-foreground">{label}</dt><dd className="tabular-nums">{number(value)} {unit}</dd></div>)}</dl>}
    </div>}
    {pending && <p role="status" className="py-1 text-tiny text-muted-foreground">Loading selectable geometry…</p>}
    {selectionDetails?.content}
  </>;
  const empty=descriptor && done===componentIds.length && !failed && componentIds.every(id=>!results[id]?.tree?.length);
  const hasDetails=Boolean(nodeDetails || pending || selectionDetails);
  return <>
    {/* No heading: the filter is the panel's top row, and stays put while the tree scrolls under it. */}
    {/* On a phone it starts folded: the model gets the screen until the person opens it. */}
    <ToolPanel id="tree" label="Features" fit="tree" resizable defaultCollapsed={mobile} hidden={!active}
      header={<TreeFilterInput dense label="Filter model" placeholder="Filter…" yieldWhileTyping value={query} onChange={changeQuery} onKeyDown={onSearchKeyDown}
        trailing={<>
          {loading && <span role="status" className="shrink-0 text-micro text-muted-foreground">Loading…</span>}
          {partControls.hiddenPartIds?.length > 0 && <Button disabled={disabled} type="button" variant="ghost" size="sm" className="h-6 shrink-0 px-1.5 text-tiny text-muted-foreground" onClick={partControls.showAllHiddenParts}>Show all</Button>}
          {/* Select's mode menu (`SelectionModes.jsx`), beside the fold chevron. */}
          {modeMenu}
          <ToolPanelCollapse/>
        </>}/>}>
      <FeatureReferencesContext.Provider value={references}><div ref={treeRef} className="flex flex-col text-tiny" aria-label="Modeling tree">
        {(error || failed>0) && <p role="alert" className="px-3 pb-2 text-micro text-muted-foreground">{error || `${failed} ${failed===1?'component is':'components are'} unavailable.`} <button type="button" className="underline" onClick={retryFailed}>Retry</button></p>}
        <div ref={listRef} className="px-1 py-1" aria-label="Model tree area"
          onClick={event=>{if(!disabled && !event.target.closest('li,button,input,[role="menu"]'))clearSelection();}}>
          {isolatedLabels.length > 0 && <div role="status" aria-label="Isolation" className="mb-1 flex min-h-7 items-center gap-2 rounded-md bg-accent/60 px-2 text-tiny">
            <Focus className="size-3 shrink-0 text-foreground" aria-hidden="true"/>
            <TooltipHint content={isolatedLabels.join(', ')} overflowOnly><span className="min-w-0 flex-1 truncate">Isolated: {isolatedLabels.join(', ')}</span></TooltipHint>
            <Button disabled={disabled} type="button" variant="ghost" size="sm" className="h-6 shrink-0 px-1.5 text-tiny" onClick={partControls.onExitAllIsolate}>Exit</Button>
          </div>}
          {searching && <p role="status" className="px-2 py-1 text-micro text-muted-foreground">{found.total > found.matches.length ? `First ${found.matches.length} of ${found.total.toLocaleString()} matches` : `${found.total} ${found.total === 1 ? 'match' : 'matches'}`}</p>}
          {searching ? found.matches.length
            ? <VirtualRows key="search" aria-label="Model search results" count={matches.length} rowHeight={TREE_ROW_DENSE_HEIGHT} pinned={searchPinned}
              rowKey={at=>matches[at].entry.node.id} rowProps={at=>({className:'min-w-0','data-search-row':matches[at].entry.node.id})} renderRow={renderSearchRow}/>
            : deferredQuery.trim() && <p className="px-3 py-6 text-center text-tiny text-muted-foreground">{`No part or feature matches “${deferredQuery.trim()}”`}</p>
          : empty && !stepRoot ? <p role="status" className="p-2 leading-relaxed text-muted-foreground">This component has no faces to inspect.</p>
          : !visibleRoots.length && implicitRoots.at(-1)?.recognitionPending ? <p role="status" className="p-2 text-tiny text-muted-foreground">Loading features…</p>
          : <VirtualRows key="tree" aria-label="Model" count={rows.length} rowHeight={TREE_ROW_DENSE_HEIGHT} pinned={treePinned}
            rowKey={at=>rows[at].key} rowProps={at=>({className:'min-w-0','aria-level':rows[at].depth+1,'data-tree-part':rows[at].node.kind === 'part' ? rows[at].node.id : undefined})}
            renderRow={renderTreeRow} registerRow={registerRow} onVisibleRange={onVisibleRows}/>}
        </div>
      </div></FeatureReferencesContext.Provider>
    </ToolPanel>
    {/* What is picked, as its own panel under the tree: it comes with a selection and goes with it. */}
    {/* Not folded away: its X clears the selection, its heading's Copy copies the reference on show,
        and the Copy at its foot the whole selection (Copy All, with several references). */}
    {hasDetails ? <ToolPanel id="reference" title={referenceTitle || 'Reference'} label="Reference details" closeLabel="Clear selection" fit="details" widthFrom="tree" maxHeight={TOOL_PANEL_REFERENCE_HEIGHT}
      collapsible={false} actions={selectionDetails?.actions} hidden={!active} onClose={clearSelection}
      footer={selectionCopy ? <ToolPanelFooterButton label={selectionCopy.label} shortcut={mobile ? '' : selectionCopy.shortcut}
        disabled={disabled} onClick={selectionCopy.onCopy}/> : null}>
      <div className="px-2 pb-1.5">{details}</div>
    </ToolPanel> : null}
  </>;
}

export default memo(ModelingTree);
