import { useDeferredValue, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { Box, Boxes, Circle, CornerUpRight, Layers, RotateCw, Shapes, Spline, SquareDashed, X } from 'lucide-react';
import { Button } from '@hardcore/ui/primitives/button';
import { TreeRowSurface, TreeRowChevron, TreeRowLabel } from '@hardcore/ui/primitives/tree-row';
import { TreeFilterHighlight, TreeFilterInput } from '@hardcore/ui/primitives/tree-filter';
import { cn } from '@hardcore/ui/utils';
import ModelPartMenu from './ModelPartMenu.jsx';
import ModelPartActions from './ModelPartActions.jsx';
import { modelingSelectionPaths } from '../../workbench/modelingSelection.js';
import InspectorSplit from '../../../kit/inspector/InspectorSplit.jsx';
import { panelScroller } from '../../../kit/inspector/FilePanelSections.jsx';
import { modelingReferenceIds } from '../../workbench/modelingTree.js';
import { implicitModelingRoots, presentModelingAssembly } from '../../workbench/modelingPresentation.js';
import { buildModelTreeSearchIndex, modelTreeSearchChain, searchModelTree } from '../../../kit/inspector/modelTreeSearch.js';

const EMPTY = [];
const NO_MATCHES = {matches:EMPTY,total:0};
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

function ModelingRow({ node, depth=0, selected, expanded, toggle, choose, disabled, partControls, feature, rowRefs, inheritedHidden=false, inheritedUnavailable=false }) {
  const Icon = icons[node.kind] || Box;
  const open = expanded.has(node.id);
  const children = (node.children || []).filter(child => child.kind !== 'curve');
  const branch = children.length > 0 || node.recognitionPending;
  // An assembly outside the isolate/picking frontier cannot select itself, but
  // its descendants can. Only a hidden owner blocks its entire subtree.
  const {hiddenByOwner,outsideFrontier,unavailable}=nodeAvailability(node,partControls,inheritedHidden,inheritedUnavailable);
  return <li className="min-w-0" ref={element => { if (element) rowRefs.current.set(node.id, element); else rowRefs.current.delete(node.id); }}>
    <ModelPartMenu node={node} controls={partControls} feature={feature} disabled={disabled}>
      <TreeRowSurface active={selected.has(node.id)} className={cn('gap-0 pr-0', hiddenByOwner && 'opacity-50')}
        onMouseEnter={() => partControls.onHoverTreeNode?.(node.selectionId || node.occurrenceId || '')}
        onMouseLeave={() => partControls.onHoverTreeNode?.('')} style={{paddingLeft:depth*14}}>
        {branch ? <button type="button" aria-label={`${open ? 'Collapse' : 'Expand'} ${node.label}`} aria-expanded={open}
          className="grid size-7 shrink-0 place-items-center rounded focus-visible:ring-2 focus-visible:ring-ring"
          onClick={()=>toggle(node)}><TreeRowChevron expanded={open}/></button> : <span className="w-7 shrink-0"/>}
        <button type="button" aria-label={`Select ${node.label}`} aria-pressed={selected.has(node.id)}
          disabled={disabled || unavailable || !(node.selectionId || node.faces?.length || node.edges?.length)}
          onClick={event=>choose(node,event)} title={node.label}
          className="flex h-full min-w-0 flex-1 items-center gap-1.5 rounded pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40">
          <Icon className="size-3.5 shrink-0 text-muted-foreground"/><TreeRowLabel className="flex-1">{node.label}</TreeRowLabel>
        </button>
        {node.selectionId && <ModelPartActions node={node} controls={partControls} disabled={disabled}/>}
      </TreeRowSurface>
    </ModelPartMenu>
    {branch && open && <ul>{children.map(child=><ModelingRow key={child.id} {...{node:child,depth:depth+1,inheritedHidden:hiddenByOwner,inheritedUnavailable:outsideFrontier,selected,expanded,toggle,choose,disabled,partControls,feature,rowRefs}}/>)}</ul>}
  </li>;
}

// A search hit is the tree row without its place in the tree: the same menu, eye
// and availability, with the owners it would sit under named instead of drawn.
function ModelingSearchRow({ match, index, selected, cursor, choose, disabled, partControls, feature }) {
  const {entry,indices}=match,{node}=entry;
  const Icon = icons[node.kind] || Box;
  const {hiddenByOwner,unavailable}=modelTreeSearchChain(index,match.at).reduce(
    (owner,step)=>nodeAvailability(step,partControls,owner.hiddenByOwner,owner.outsideFrontier),{hiddenByOwner:false,outsideFrontier:false});
  return <li className="min-w-0" data-search-row={node.id}>
    <ModelPartMenu node={node} controls={partControls} feature={feature} disabled={disabled}>
      <TreeRowSurface active={selected.has(node.id)} cursor={cursor} className={cn('gap-0 pr-0', hiddenByOwner && 'opacity-50')}
        onMouseEnter={() => partControls.onHoverTreeNode?.(node.selectionId || node.occurrenceId || '')}
        onMouseLeave={() => partControls.onHoverTreeNode?.('')}>
        <button type="button" aria-label={`Select ${node.label}`} aria-pressed={selected.has(node.id)}
          disabled={disabled || unavailable || !(node.selectionId || node.faces?.length || node.edges?.length)}
          onClick={event=>choose(node,event)} title={`${entry.prefix}${node.label}`}
          className="flex h-full min-w-0 flex-1 items-center gap-1.5 rounded pl-2 pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40">
          <Icon className="size-3.5 shrink-0 text-muted-foreground"/>
          {/* Name first: in a narrow panel a deep owner path takes the truncation, never the name. */}
          <TreeRowLabel className="max-w-full shrink-0"><TreeFilterHighlight indices={indices} text={entry.label}/></TreeRowLabel>
          {entry.prefix && <TreeRowLabel className="flex-1 text-micro text-muted-foreground">{entry.prefix.slice(0,-1)}</TreeRowLabel>}
        </button>
        {node.selectionId && <ModelPartActions node={node} controls={partControls} disabled={disabled}/>}
      </TreeRowSurface>
    </ModelPartMenu>
  </li>;
}

/** Read-only geometry inference; assembly instances share recognition, never selection IDs. */
export default function ModelingTree({ modeling, active, disabled, references=EMPTY, selectedReferenceIds=EMPTY, selectedPartIds=EMPTY, onLoadTopology, onRequestRecognition, onVisibleFeatureTargetsChange, onSelect, onClearSelection, stepRoot, selectedReferences, selectionDetails, activeTreeNodeScrollKey, partControls={} }) {
  const {descriptor,results,error,retryFailed}=modeling;
  const [selected,setSelected]=useState(null),[pending,setPending]=useState(null),[localExpanded,setLocalExpanded]=useState(new Set());
  const tree=useMemo(()=>presentModelingAssembly(descriptor,results,stepRoot),[descriptor,results,stepRoot]);
  const implicitRoots=useMemo(()=>implicitModelingRoots(tree),[tree]);
  const visibleRoots=implicitRoots.length ? implicitRoots.at(-1).children || EMPTY : tree;
  const implicitOwner=implicitRoots.reduce((owner,node)=>nodeAvailability(node,partControls,owner.hiddenByOwner,owner.outsideFrontier),{hiddenByOwner:false,outsideFrontier:false});
  const componentIds=useMemo(()=>[...new Set(descriptor?.occurrences.map(o=>o.component)||[])],[descriptor]);
  const expanded=useMemo(()=>new Set([...localExpanded,...implicitRoots.map(node=>node.id),...(partControls.expandedTreeNodeIds || EMPTY).map(id=>`model:${id}`)]),[localExpanded,implicitRoots,partControls.expandedTreeNodeIds]);
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
  const [query,setQuery]=useState(''),[cursor,setCursor]=useState(null);
  const searching=query.trim() !== '',deferredQuery=useDeferredValue(query);
  const searchIndex=useMemo(()=>searching ? buildModelTreeSearchIndex(tree) : null,[searching,tree]);
  const found=useMemo(()=>searchIndex ? searchModelTree(searchIndex,deferredQuery) : NO_MATCHES,[searchIndex,deferredQuery]);
  const listRef=useRef(null),resumeScroll=useRef(0);
  const changeQuery=value=>{
    if(!searching && value.trim() && listRef.current)resumeScroll.current=panelScroller(listRef.current).scrollTop;
    setQuery(value);setCursor(null);
  };
  // Back where the tree was; a hit selected meanwhile is then scrolled to by the reveal below.
  useLayoutEffect(()=>{if(!searching && listRef.current)panelScroller(listRef.current).scrollTop=resumeScroll.current;},[searching]);
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
  },[active,revealKey,paths,expanded,picked,partControls.onToggleTreeNode,searching]);

  const requestedOccurrences=useMemo(()=>{
    if(!active || disabled)return EMPTY;
    const requested=[];
    const visit=(nodes,inheritedHidden=false,inheritedUnavailable=false)=>{for(const node of nodes){
      if(!expanded.has(node.id))continue;
      const {hiddenByOwner,outsideFrontier,unavailable}=nodeAvailability(node,partControls,inheritedHidden,inheritedUnavailable);
      if(node.kind === 'part' && node.occurrenceId && !unavailable)requested.push(node.occurrenceId);
      visit(node.children || EMPTY,hiddenByOwner,outsideFrontier);
    }};
    visit(tree);
    return [...new Set(requested)].sort();
  },[active,disabled,tree,expanded,partControls.hiddenPartIds,partControls.selectableNodeIds]);
  const requestKey=JSON.stringify(requestedOccurrences);
  useEffect(()=>{onRequestRecognition?.(JSON.parse(requestKey));},[requestKey,onRequestRecognition]);

  const visibleFeatureTargets=useMemo(()=>{
    const targets=[];
    const visit=(nodes,inheritedHidden=false,inheritedUnavailable=false)=>{for(const node of nodes){
      if(node.kind === 'curve')continue;
      const {hiddenByOwner,outsideFrontier,unavailable}=nodeAvailability(node,partControls,inheritedHidden,inheritedUnavailable);
      // Children first: a visible profile wins over its feature; its parent is
      // retained as the fallback for canonical faces outside that profile.
      if(expanded.has(node.id))visit(node.children || EMPTY,hiddenByOwner,outsideFrontier);
      if(!node.selectionId && !unavailable){
        const referenceIds=modelingReferenceIds(node,node.occurrenceId,references);
        if(referenceIds.length)targets.push({nodeId:node.id,referenceIds});
      }
    }};
    visit(tree);
    return targets;
  },[tree,expanded,references,partControls.hiddenPartIds,partControls.selectableNodeIds]);
  const featureTargetKey=JSON.stringify(visibleFeatureTargets);
  useEffect(()=>{onVisibleFeatureTargetsChange?.(JSON.parse(featureTargetKey));},[featureTargetKey,onVisibleFeatureTargetsChange]);
  useEffect(()=>()=>onVisibleFeatureTargetsChange?.([]),[onVisibleFeatureTargetsChange]);

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
  const cursorId=found.matches.some(match=>match.entry.node.id === cursor) ? cursor : found.matches[0]?.entry.node.id ?? null;
  useEffect(()=>{if(cursorId)listRef.current?.querySelector(`[data-search-row="${CSS.escape(cursorId)}"]`)?.scrollIntoView?.({block:'nearest'});},[cursorId]);
  const onSearchKeyDown=event=>{
    if(event.key === 'Escape' && query){event.preventDefault();event.stopPropagation();changeQuery('');return;}
    if(!found.matches.length)return;
    const at=found.matches.findIndex(match=>match.entry.node.id === cursorId);
    if(event.key === 'ArrowDown' || event.key === 'ArrowUp'){
      event.preventDefault();
      setCursor(found.matches[Math.min(Math.max(at+(event.key === 'ArrowDown' ? 1 : -1),0),found.matches.length-1)].entry.node.id);
    } else if(event.key === 'Enter' && at >= 0){
      event.preventDefault();
      listRef.current?.querySelector(`[data-search-row="${CSS.escape(cursorId)}"] button[aria-pressed]:not(:disabled)`)?.click();
    }
  };
  const highlighted=new Set(showDetails ? [selected.id] : paths.map(path=>path.at(-1).id));
  const selectedNode=showDetails ? selected : paths.length === 1 ? paths[0].at(-1) : null;
  const nodeDetails=selectedNode && (selectedNode.summary || selectedNode.note || selectedNode.measurements?.length);
  const details=showDetails && selected.edges?.length === 1 && !pending && selectionDetails ? selectionDetails : <>
    {nodeDetails && (showDetails || !selectionDetails) && <div className="mb-2 space-y-1 text-tiny" aria-label="Feature details">
      {showDetails && <p>{selectedNode.label}</p>}
      {selectedNode.summary && <p className="text-muted-foreground">{selectedNode.summary}</p>}
      {selectedNode.note && <p className="text-muted-foreground">{selectedNode.note}</p>}
      {!!selectedNode.measurements?.length && <dl>{selectedNode.measurements.map(([label,value,unit])=><div key={label} className="grid grid-cols-[5rem_minmax(0,1fr)] gap-2 py-1"><dt className="text-muted-foreground">{label}</dt><dd className="tabular-nums">{number(value)} {unit}</dd></div>)}</dl>}
    </div>}
    {pending && <p role="status" className="py-1 text-tiny text-muted-foreground">Loading selectable geometry…</p>}
    {selectionDetails}
  </>;
  const empty=descriptor && done===componentIds.length && !failed && componentIds.every(id=>!results[id]?.tree?.length);
  return <div className="flex flex-col text-xs" aria-label="Modeling tree">
    <TreeFilterInput className="h-7" label="Filter model" placeholder="Filter model…" value={query} onChange={changeQuery} onKeyDown={onSearchKeyDown}
      trailing={<>
        {partControls.hiddenPartIds?.length > 0 && <Button disabled={disabled} type="button" variant="ghost" size="sm" className="h-6 shrink-0 px-1.5 text-tiny text-muted-foreground" onClick={partControls.showAllHiddenParts}>Show all</Button>}
        {partControls.focusedNodeIds?.length > 0 && <Button disabled={disabled} type="button" variant="ghost" size="sm" className="h-6 shrink-0 px-1.5 text-tiny text-muted-foreground" onClick={partControls.onExitAllIsolate}>Exit isolate</Button>}
      </>}/>
    {(error || failed>0) && <p role="alert" className="px-3 pb-2 text-micro text-muted-foreground">{error || `${failed} ${failed===1?'component is':'components are'} unavailable.`} <button type="button" className="underline" onClick={retryFailed}>Retry</button></p>}
    <InspectorSplit title="Reference"
      actions={<Button type="button" variant="ghost" size="icon-xs" aria-label="Clear selection" title="Clear selection" disabled={disabled} onClick={clearSelection}><X className="size-3.5" aria-hidden="true"/></Button>}
      label="Reference details" details={nodeDetails || pending || selectionDetails ? details : null}>
      <div ref={listRef} className="px-1 py-1" aria-label="Model tree area"
        onClick={event=>{if(!disabled && !event.target.closest('li,button,input,[role="menu"]'))clearSelection();}}>
        {searching && <p role="status" className="px-2 py-1 text-micro text-muted-foreground">{found.total > found.matches.length ? `First ${found.matches.length} of ${found.total.toLocaleString()} matches` : `${found.total} ${found.total === 1 ? 'match' : 'matches'}`}</p>}
        {searching ? found.matches.length
          ? <ul aria-label="Model search results">{found.matches.map(match=><ModelingSearchRow key={match.entry.node.id} {...{match,index:searchIndex,selected:highlighted,cursor:match.entry.node.id === cursorId,choose,disabled,partControls,feature}}/>)}</ul>
          : deferredQuery.trim() && <p className="px-3 py-6 text-center text-xs text-muted-foreground">{`No part or feature matches “${deferredQuery.trim()}”`}</p>
        : empty && !stepRoot ? <p role="status" className="p-2 leading-relaxed text-muted-foreground">This component has no faces to inspect.</p>
        : !visibleRoots.length && implicitRoots.at(-1)?.recognitionPending ? <p role="status" className="p-2 text-tiny text-muted-foreground">Loading features…</p>
        : <ul aria-label="Model">{visibleRoots.map(node=><ModelingRow key={node.id} {...{node,selected:highlighted,expanded,choose,disabled,partControls,feature,rowRefs,toggle,inheritedHidden:implicitOwner.hiddenByOwner,inheritedUnavailable:implicitOwner.outsideFrontier}}/>)}</ul>}
      </div>
    </InspectorSplit>
  </div>;
}
