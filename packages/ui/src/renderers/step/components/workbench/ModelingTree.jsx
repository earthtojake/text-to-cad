import { TooltipHint } from "@hardcore/ui/primitives/tooltip";
import { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Boxes, Circle, CornerUpRight, Focus, Layers, RotateCw, Shapes, Spline, SquareDashed } from 'lucide-react';
import { Button } from '@hardcore/ui/primitives/button';
import { TreeRowSurface, TreeRowChevron, TreeRowLabel } from '@hardcore/ui/primitives/tree-row';
import { TreeFilterHighlight, TreeFilterInput } from '@hardcore/ui/primitives/tree-filter';
import { cn } from '@hardcore/ui/utils';
import ModelPartMenu from './ModelPartMenu.jsx';
import ModelPartActions from './ModelPartActions.jsx';
import { modelingSelectionPaths } from '../../workbench/modelingSelection.js';
import ToolPanel from '../../../kit/tools/ToolPanel.jsx';
import { modelingReferenceIds } from '../../workbench/modelingTree.js';
import { implicitModelingRoots, presentModelingAssembly } from '../../workbench/modelingPresentation.js';
import { modelTreeSearchChain, useTreeSearch } from '../../../kit/inspector/modelTreeSearch.js';

const EMPTY = [];
const icons = {part:Box,assembly:Boxes,group:Boxes,boss:Layers,pocket:Shapes,hole:Circle,body:Box,extrude:Layers,loft:Layers,cut:Shapes,revolve:RotateCw,round:CornerUpRight,profile:SquareDashed,curve:Spline,remainder:Box};
const number = n => n.toLocaleString(undefined,{maximumFractionDigits:3});

function nodeAvailability(node, controls, inheritedHidden=false, inheritedUnavailable=false) {
  const hidden = node.leafPartIds?.length > 0 && node.leafPartIds.every(id => controls.hiddenPartIds?.includes(id));
  const hiddenByOwner = inheritedHidden || hidden;
  const outsideFrontier = node.selectionId
    ? controls.selectableNodeIds && !controls.selectableNodeIds.includes(node.selectionId)
    : inheritedUnavailable;
  return {hiddenByOwner,outsideFrontier,unavailable:hiddenByOwner || outsideFrontier};
}

// Selected rows that touch read as ONE block: a run of consecutive visible selected rows is
// rounded only at its top and bottom, so a multi-select is a unit rather than a stack of pills.
const NO_JOINS = new Map();
function joinedCorners(join) {
  if (!join) return undefined;
  return {
    ...(join.above ? { borderTopLeftRadius: 0, borderTopRightRadius: 0 } : {}),
    ...(join.below ? { borderBottomLeftRadius: 0, borderBottomRightRadius: 0 } : {}),
  };
}
function selectionJoins(orderedIds, highlighted) {
  const joins = new Map();
  orderedIds.forEach((id, index) => {
    if (!highlighted.has(id)) return;
    const above = index > 0 && highlighted.has(orderedIds[index - 1]);
    const below = index < orderedIds.length - 1 && highlighted.has(orderedIds[index + 1]);
    if (above || below) joins.set(id, { above, below });
  });
  return joins;
}
function visibleRowOrder(nodes, expanded, out = []) {
  for (const node of nodes) {
    out.push(node.id);
    const children = (node.children || []).filter(child => child.kind !== 'curve');
    if (children.length && expanded.has(node.id)) visibleRowOrder(children, expanded, out);
  }
  return out;
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
  if (locked) return <span aria-hidden="true" data-disclosure-locked={open ? "open" : "shut"} className="grid h-7 w-5 shrink-0 place-items-center opacity-50"><TreeRowChevron expanded={open}/></span>;
  return <button type="button" aria-label={`${open ? 'Collapse' : 'Expand'} ${node.label}`} aria-expanded={open}
    className="grid h-7 w-5 shrink-0 place-items-center rounded focus-visible:ring-2 focus-visible:ring-ring"
    onClick={()=>toggle(node)}><TreeRowChevron expanded={open}/></button>;
}

function ModelingRow({ node, depth=0, selected, joins=NO_JOINS, expanded, locked=false, toggle, choose, disabled, partControls, feature, rowRefs, inheritedHidden=false, inheritedUnavailable=false }) {
  const Icon = icons[node.kind] || Box;
  const open = expanded.has(node.id);
  const children = (node.children || []).filter(child => child.kind !== 'curve');
  const branch = children.length > 0 || node.recognitionPending;
  // An assembly outside the isolate/picking frontier cannot select itself, but
  // its descendants can. Only a hidden owner blocks its entire subtree.
  const {hiddenByOwner,outsideFrontier,unavailable}=nodeAvailability(node,partControls,inheritedHidden,inheritedUnavailable);
  return <li className="min-w-0" data-tree-part={node.kind === 'part' ? node.id : undefined}
    ref={element => { if (element) rowRefs.current.set(node.id, element); else rowRefs.current.delete(node.id); }}>
    <ModelPartMenu node={node} controls={partControls} feature={feature} disabled={disabled}>
      <TreeRowSurface active={selected.has(node.id)} className={cn('group/row gap-0 pr-0', hiddenByOwner && 'opacity-50')}
        onMouseEnter={() => partControls.onHoverTreeNode?.(node.selectionId || node.occurrenceId || '')}
        onMouseLeave={() => partControls.onHoverTreeNode?.('')} style={{paddingLeft:depth*12, ...joinedCorners(joins.get(node.id))}}>
        {branch ? <Disclosure node={node} open={open} locked={locked} toggle={toggle}/> : <span className="w-5 shrink-0"/>}
        <TooltipHint content={node.label} overflowOnly><button type="button" aria-label={`Select ${node.label}`} aria-pressed={selected.has(node.id)}
          disabled={disabled || unavailable || !(node.selectionId || node.memberSelectionIds?.length || node.faces?.length || node.edges?.length)}
          onClick={event=>{if(event.detail < 2)choose(node,event);}} onDoubleClick={event=>choose(node,event)}
          className="flex h-full min-w-0 flex-1 items-center gap-1 rounded pr-1 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40">
          <Icon className="size-3.5 shrink-0 text-muted-foreground"/><TreeRowLabel className="flex-1">{node.label}</TreeRowLabel>
        </button></TooltipHint>
        {node.selectionId && <ModelPartActions node={node} controls={partControls} disabled={disabled}/>}
      </TreeRowSurface>
    </ModelPartMenu>
    {branch && open && <ul>{children.map(child=><ModelingRow key={child.id} {...{node:child,depth:depth+1,inheritedHidden:hiddenByOwner,inheritedUnavailable:outsideFrontier,selected,joins,expanded,locked,toggle,choose,disabled,partControls,feature,rowRefs}}/>)}</ul>}
  </li>;
}

// A search hit is the tree row without its place in the tree: the same menu, eye
// and availability, with the owners it would sit under named instead of drawn.
function ModelingSearchRow({ match, index, selected, joins=NO_JOINS, cursor, choose, disabled, partControls, feature }) {
  const {entry,indices}=match,{node}=entry;
  const Icon = icons[node.kind] || Box;
  const {hiddenByOwner,unavailable}=modelTreeSearchChain(index,match.at).reduce(
    (owner,step)=>nodeAvailability(step,partControls,owner.hiddenByOwner,owner.outsideFrontier),{hiddenByOwner:false,outsideFrontier:false});
  return <li className="min-w-0" data-search-row={node.id}>
    <ModelPartMenu node={node} controls={partControls} feature={feature} disabled={disabled}>
      <TreeRowSurface active={selected.has(node.id)} cursor={cursor} className={cn('group/row gap-0 pr-0', hiddenByOwner && 'opacity-50')}
        onMouseEnter={() => partControls.onHoverTreeNode?.(node.selectionId || node.occurrenceId || '')}
        onMouseLeave={() => partControls.onHoverTreeNode?.('')} style={joinedCorners(joins.get(node.id))}>
        <TooltipHint content={`${entry.prefix}${node.label}`} overflowOnly><button type="button" aria-label={`Select ${node.label}`} aria-pressed={selected.has(node.id)}
          disabled={disabled || unavailable || !(node.selectionId || node.faces?.length || node.edges?.length)}
          onClick={event=>{if(event.detail < 2)choose(node,event);}} onDoubleClick={event=>choose(node,event)}
          className="flex h-full min-w-0 flex-1 items-center gap-1.5 rounded pl-2 pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40">
          <Icon className="size-3.5 shrink-0 text-muted-foreground"/>
          {/* Name first: in a narrow panel a deep owner path takes the truncation, never the name. */}
          <TreeRowLabel className="max-w-full shrink-0"><TreeFilterHighlight indices={indices} text={entry.label}/></TreeRowLabel>
          {entry.prefix && <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{entry.prefix.slice(0,-1)}</TreeRowLabel>}
        </button></TooltipHint>
        {node.selectionId && <ModelPartActions node={node} controls={partControls} disabled={disabled}/>}
      </TreeRowSurface>
    </ModelPartMenu>
  </li>;
}

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
export default function ModelingTree({ modeling, active, disabled, mode='all', loading=false, references=EMPTY, selectedReferenceIds=EMPTY, selectedPartIds=EMPTY, onLoadTopology, onRequestRecognition, onSelect, onClearSelection, stepRoot, selectedReferences, selectionDetails, activeTreeNodeScrollKey, partControls={} }) {
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
  const implicitOwner=implicitRoots.reduce((owner,node)=>nodeAvailability(node,partControls,owner.hiddenByOwner,owner.outsideFrontier),{hiddenByOwner:false,outsideFrontier:false});
  const componentIds=useMemo(()=>[...new Set(descriptor?.occurrences.map(o=>o.component)||[])],[descriptor]);
  const expanded=useMemo(()=>lockedExpansion ? new Set([...lockedExpansion,...implicitRoots.map(node=>node.id)])
    : new Set([...localExpanded,...implicitRoots.map(node=>node.id),...(partControls.expandedTreeNodeIds || EMPTY).map(id=>`model:${id}`)]),
  [lockedExpansion,localExpanded,implicitRoots,partControls.expandedTreeNodeIds]);
  const openedRoots=useRef(new Set());
  useEffect(()=>{
    if(!active || disabled)return;
    let owner={hiddenByOwner:false,outsideFrontier:false};
    for(const node of implicitRoots){
      owner=nodeAvailability(node,partControls,owner.hiddenByOwner,owner.outsideFrontier);
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
  },[active,disabled,implicitRoots,onLoadTopology,partControls.expandedTreeNodeIds,partControls.onToggleTreeNode,partControls.hiddenPartIds,partControls.selectableNodeIds]);
  const rowRefs=useRef(new Map());
  // Search is a second view of the same tree. Typing never touches expansion,
  // which is also the picking frontier and the topology request; the rows
  // unmount so a large open tree is not re-rendered per keystroke.
  const {query,searching,deferredQuery,index:searchIndex,found,cursorId,listRef,changeQuery,onKeyDown:onSearchKeyDown}=useTreeSearch(tree);
  useEffect(()=>{
    if(!topologyMode || !active || disabled || searching || !listRef.current)return undefined;
    const rows=[...listRef.current.querySelectorAll('[data-tree-part]')];
    const mark=ids=>setSeenParts(current=>ids.every(id=>current.has(id)) ? current : new Set([...current,...ids]));
    if(typeof IntersectionObserver === 'undefined'){mark(rows.map(row=>row.dataset.treePart));return undefined;}
    const observer=new IntersectionObserver(entries=>{
      const ids=entries.filter(entry=>entry.isIntersecting).map(entry=>entry.target.dataset.treePart);
      if(ids.length)mark(ids);
    },{root:listRef.current.closest('[data-tool-panel-body]')});
    for(const row of rows)observer.observe(row);
    return ()=>observer.disconnect();
  },[topologyMode,active,disabled,searching,tree,listRef]);
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
    // A search hit's owners open at once, so the selection is always a row the
    // tree holds; the one scroll waits for the tree to be back on screen.
    if(waitingForFeature || searching)return;
    const row=rowRefs.current.get(target.id);
    if(row){row.scrollIntoView?.({block:'nearest'});reveal.current.complete=true;}
  },[active,revealKey,paths,expanded,locked,picked,partControls.onToggleTreeNode,searching]);

  const requestedOccurrences=useMemo(()=>{
    if(!active || disabled)return EMPTY;
    const requested=[];
    const visit=(nodes,inheritedHidden=false,inheritedUnavailable=false)=>{for(const node of nodes){
      if(!expanded.has(node.id))continue;
      const {hiddenByOwner,outsideFrontier,unavailable}=nodeAvailability(node,partControls,inheritedHidden,inheritedUnavailable);
      if(node.kind === 'part' && node.occurrenceId && !unavailable && (!topologyMode || seenParts.has(node.id)))requested.push(node.occurrenceId);
      visit(node.children || EMPTY,hiddenByOwner,outsideFrontier);
    }};
    visit(tree);
    return [...new Set(requested)].sort();
  },[active,disabled,tree,expanded,topologyMode,seenParts,partControls.hiddenPartIds,partControls.selectableNodeIds]);
  const requestKey=JSON.stringify(requestedOccurrences);
  useEffect(()=>{onRequestRecognition?.(JSON.parse(requestKey));},[requestKey,onRequestRecognition]);

  const done=componentIds.filter(id=>results[id]).length;
  const failed=componentIds.filter(id=>results[id]?.error).length;
  useEffect(()=>{if(!active || disabled)setPending(null);},[active,disabled]);
  useEffect(()=>{
    if(!pending || !active || disabled)return;
    if(pending.selectionKey !== selectionKey){setPending(null);return;}
    const ids=modelingReferenceIds(pending,pending.occurrenceId,references);
    if(ids.length){onSelect?.(ids);setPending(null);}
  },[pending,active,disabled,references,onSelect,selectionKey]);
  const choose=(node,event)=>{
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
  };
  const toggle=node=>{
    if(node.selectionId && partControls.onToggleTreeNode){partControls.onToggleTreeNode(node.selectionId);return;}
    setLocalExpanded(current=>{const next=new Set(current);if(next.has(node.id))next.delete(node.id);else next.add(node.id);return next;});
  };
  const clearSelection=()=>{setSelected(null);setPending(null);onClearSelection?.();};
  // What a feature row's menu needs of the tree: the row's faces as reference ids, how to load
  // them, and the row's own click, so its Select is the click rather than a second opinion.
  const feature={referenceIds:node=>modelingReferenceIds(node,node.occurrenceId,references),loadTopology:onLoadTopology,choose};
  const highlighted=new Set(showDetails ? [selected.id] : paths.map(path=>path.at(-1).id));
  // Its members are not rendered while it is collapsed, so the row itself carries
  // their selection; anything less and selecting a folded row looks like a no-op.
  for(const node of foldedRows)if(node.memberSelectionIds.every(id=>selectedPartIds.includes(id)))highlighted.add(node.id);
  const joins=selectionJoins(visibleRowOrder(visibleRoots,expanded),highlighted);
  const searchJoins=searching?selectionJoins(found.matches.map(match=>match.entry.node.id),highlighted):NO_JOINS;
  const isolatedLabels=(partControls.focusedNodeIds||[]).map(id=>findNodeLabel(visibleRoots,id)||id);
  const selectedNode=showDetails ? selected : paths.length === 1 ? paths[0].at(-1) : null;
  const nodeDetails=selectedNode && (selectedNode.summary || selectedNode.note || selectedNode.measurements?.length);
  // The Reference panel's heading is the reference being read (`useStepReference`: its name and
  // id, or the picker over several); a feature row picked in the tree heads it by its label until
  // its faces are what is selected.
  const referenceTitle=selectionDetails?.title ?? (selectedNode ? <span className="block truncate">{selectedNode.label}</span> : null);
  const details=showDetails && selected.edges?.length === 1 && !pending && selectionDetails ? selectionDetails.content : <>
    {nodeDetails && (showDetails || !selectionDetails) && <div className="mb-2 space-y-1 text-tiny" aria-label="Feature details">
      {showDetails && selectionDetails && <p>{selectedNode.label}</p>}
      {selectedNode.summary && <p className="text-muted-foreground">{selectedNode.summary}</p>}
      {selectedNode.note && <p className="text-muted-foreground">{selectedNode.note}</p>}
      {!!selectedNode.measurements?.length && <dl>{selectedNode.measurements.map(([label,value,unit])=><div key={label} className="grid grid-cols-[4rem_minmax(0,1fr)] gap-2 py-1"><dt className="text-muted-foreground">{label}</dt><dd className="tabular-nums">{number(value)} {unit}</dd></div>)}</dl>}
    </div>}
    {pending && <p role="status" className="py-1 text-tiny text-muted-foreground">Loading selectable geometry…</p>}
    {selectionDetails?.content}
  </>;
  const empty=descriptor && done===componentIds.length && !failed && componentIds.every(id=>!results[id]?.tree?.length);
  const hasDetails=Boolean(nodeDetails || pending || selectionDetails);
  return <>
    {/* No heading: the filter is the panel's top row, and stays put while the tree scrolls under it. */}
    <ToolPanel label="Features" fit="tree" hidden={!active}
      header={<TreeFilterInput className="px-1" label="Filter model" placeholder="Filter model…" value={query} onChange={changeQuery} onKeyDown={onSearchKeyDown}
        trailing={<>
          {loading && <span role="status" className="shrink-0 text-micro text-muted-foreground">Loading…</span>}
          {partControls.hiddenPartIds?.length > 0 && <Button disabled={disabled} type="button" variant="ghost" size="sm" className="h-6 shrink-0 px-1.5 text-tiny text-muted-foreground" onClick={partControls.showAllHiddenParts}>Show all</Button>}
        </>}/>}>
      <div className="flex flex-col text-xs" aria-label="Modeling tree" data-tree-mode={mode}>
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
            ? <ul aria-label="Model search results">{found.matches.map(match=><ModelingSearchRow key={match.entry.node.id} {...{match,index:searchIndex,selected:highlighted,joins:searchJoins,cursor:match.entry.node.id === cursorId,choose,disabled,partControls,feature}}/>)}</ul>
            : deferredQuery.trim() && <p className="px-3 py-6 text-center text-xs text-muted-foreground">{`No part or feature matches “${deferredQuery.trim()}”`}</p>
          : empty && !stepRoot ? <p role="status" className="p-2 leading-relaxed text-muted-foreground">This component has no faces to inspect.</p>
          : !visibleRoots.length && implicitRoots.at(-1)?.recognitionPending ? <p role="status" className="p-2 text-tiny text-muted-foreground">Loading features…</p>
          : <ul aria-label="Model">{visibleRoots.map(node=><ModelingRow key={node.id} {...{node,selected:highlighted,joins,expanded,locked,choose,disabled,partControls,feature,rowRefs,toggle,inheritedHidden:implicitOwner.hiddenByOwner,inheritedUnavailable:implicitOwner.outsideFrontier}}/>)}</ul>}
        </div>
      </div>
    </ToolPanel>
    {/* What is picked, as its own panel under the tree: it comes with a selection and goes with it. */}
    {hasDetails ? <ToolPanel title={referenceTitle || 'Reference'} label="Reference details" closeLabel="Clear selection" fit="details" capped hidden={!active} onClose={clearSelection}>
      <div className="px-2 pb-2">{details}</div>
    </ToolPanel> : null}
  </>;
}
