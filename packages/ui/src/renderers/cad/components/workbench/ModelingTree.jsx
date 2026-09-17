import { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Boxes, Circle, CornerUpRight, Layers, RotateCw, Shapes, Spline, SquareDashed, X } from 'lucide-react';
import { Button } from '@hardcore/ui/primitives/button';
import { TreeRowSurface, TreeRowChevron, TreeRowLabel } from '@hardcore/ui/primitives/tree-row';
import { selectionSummary } from '../../workbench/selectionSummary.js';
import { cn } from '@hardcore/ui/utils';
import ModelPartMenu from './ModelPartMenu.jsx';
import ModelPartActions from './ModelPartActions.jsx';
import { modelingSelectionPaths } from '../../workbench/modelingSelection.js';
import InspectorSplit from './InspectorSplit.jsx';
import { modelingReferenceIds } from '../../workbench/modelingTree.js';
import { presentModelingAssembly } from '../../workbench/modelingPresentation.js';

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

function ModelingRow({ node, depth=0, selected, expanded, toggle, choose, disabled, partControls, rowRefs, inheritedHidden=false, inheritedUnavailable=false }) {
  const Icon = icons[node.kind] || Box;
  const open = expanded.has(node.id);
  const children = (node.children || []).filter(child => child.kind !== 'curve');
  const branch = children.length > 0 || node.recognitionPending;
  // An assembly outside the isolate/picking frontier cannot select itself, but
  // its descendants can. Only a hidden owner blocks its entire subtree.
  const {hiddenByOwner,outsideFrontier,unavailable}=nodeAvailability(node,partControls,inheritedHidden,inheritedUnavailable);
  return <li className="min-w-0" ref={element => { if (element) rowRefs.current.set(node.id, element); else rowRefs.current.delete(node.id); }}>
    <ModelPartMenu node={node} controls={partControls} disabled={disabled} selectDisabled={disabled || unavailable} selected={selected.has(node.id)} onSelect={event=>choose(node,event)}>
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
    {branch && open && <ul>{children.map(child=><ModelingRow key={child.id} {...{node:child,depth:depth+1,inheritedHidden:hiddenByOwner,inheritedUnavailable:outsideFrontier,selected,expanded,toggle,choose,disabled,partControls,rowRefs}}/>)}</ul>}
  </li>;
}

/** Read-only geometry inference; assembly instances share recognition, never selection IDs. */
export default function ModelingTree({ modeling, active, disabled, references=EMPTY, selectedReferenceIds=EMPTY, selectedPartIds=EMPTY, onLoadTopology, onRequestRecognition, onVisibleFeatureTargetsChange, onSelect, onClearSelection, stepRoot, selectedReferences, selectionDetails, activeTreeNodeScrollKey, partControls={} }) {
  const {descriptor,results,error,retryFailed}=modeling;
  const [selected,setSelected]=useState(null),[pending,setPending]=useState(null),[localExpanded,setLocalExpanded]=useState(new Set());
  const tree=useMemo(()=>presentModelingAssembly(descriptor,results,stepRoot),[descriptor,results,stepRoot]);
  const componentIds=useMemo(()=>[...new Set(descriptor?.occurrences.map(o=>o.component)||[])],[descriptor]);
  const expanded=useMemo(()=>new Set([...localExpanded,...(partControls.expandedTreeNodeIds || EMPTY).map(id=>`model:${id}`)]),[localExpanded,partControls.expandedTreeNodeIds]);
  const rowRefs=useRef(new Map());
  const picked=useMemo(()=>selectedReferences || references.filter(ref=>selectedReferenceIds.includes(ref.id)),[selectedReferences,references,selectedReferenceIds]);
  const summary=selectionSummary(picked,descriptor?.occurrences);
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
    if(waitingForFeature)return;
    const row=rowRefs.current.get(target.id);
    if(row){row.scrollIntoView?.({block:'nearest'});reveal.current.complete=true;}
  },[active,revealKey,paths,expanded,picked,partControls.onToggleTreeNode]);

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
  const highlighted=new Set(showDetails ? [selected.id] : paths.map(path=>path.at(-1).id));
  const selectedNode=showDetails ? selected : paths.length === 1 ? paths[0].at(-1) : null;
  const nodeDetails=selectedNode && (selectedNode.summary || selectedNode.note || selectedNode.measurements?.length);
  const details=showDetails && selected.edges?.length === 1 && !pending && selectionDetails ? selectionDetails : <>
    {nodeDetails && <div className="space-y-3 p-3" aria-label="Modeling details">
      {selectedNode.summary && <p className="text-muted-foreground">{selectedNode.summary}</p>}
      {selectedNode.note && <p className="text-muted-foreground">{selectedNode.note}</p>}
      {!!selectedNode.measurements?.length && <dl className="space-y-2">{selectedNode.measurements.map(([label,value,unit])=><div key={label} className="flex flex-wrap justify-between gap-x-3 gap-y-1"><dt className="text-muted-foreground">{label}</dt><dd className="tabular-nums">{number(value)} {unit}</dd></div>)}</dl>}
    </div>}
    {pending && <p role="status" className="p-3 text-micro text-muted-foreground">Loading selectable geometry…</p>}
    {selectionDetails}
  </>;
  const empty=descriptor && done===componentIds.length && !failed && componentIds.every(id=>!results[id]?.tree?.length);
  return <div className="flex h-full min-h-0 flex-col text-xs" aria-label="Modeling tree">
    <div className="flex h-8 shrink-0 items-center justify-between gap-3 px-3 text-micro text-muted-foreground" aria-label="Model tree summary">
      <span>{tree.length} {tree.length === 1 ? 'feature' : 'features'}</span>
      <div className="flex items-center gap-3">
        {partControls.hiddenPartIds?.length > 0 && <button disabled={disabled} type="button" className="hover:text-foreground" onClick={partControls.showAllHiddenParts}>Show all</button>}
        {partControls.focusedNodeIds?.length > 0 && <button disabled={disabled} type="button" className="hover:text-foreground" onClick={partControls.onExitAllIsolate}>Exit isolate</button>}
      </div>
    </div>
    {(error || failed>0) && <p role="alert" className="px-3 pb-2 text-micro text-muted-foreground">{error || `${failed} ${failed===1?'component is':'components are'} unavailable.`} <button type="button" className="underline" onClick={retryFailed}>Retry</button></p>}
    <InspectorSplit title={summary.label ? <span className="flex min-w-0 items-center gap-1">
      <span className="max-w-full shrink-0 truncate">{summary.label}</span>
      {summary.context && <span className="truncate text-muted-foreground">· {summary.context}</span>}
    </span> : showDetails ? selected?.label : 'Selection'}
      titleTooltip={summary.label ? [summary.label,summary.context].filter(Boolean).join(' · ') : undefined}
      actions={summary.label && onClearSelection ? <Button type="button" variant="ghost" size="icon-xs" aria-label="Clear selection" title="Clear selection" disabled={disabled} onClick={()=>{setSelected(null);setPending(null);onClearSelection();}}><X className="size-3.5" aria-hidden="true"/></Button> : null}
      label="Modeling details" details={nodeDetails || pending || selectionDetails ? details : null}>
      <div className="min-h-0 flex-1 overflow-auto px-1 py-1">
        {empty && !stepRoot ? <p role="status" className="p-2 leading-relaxed text-muted-foreground">This component has no faces to inspect.</p> : <ul aria-label="Model">{tree.map(node=><ModelingRow key={node.id} {...{node,selected:highlighted,expanded,choose,disabled,partControls,rowRefs,toggle}}/>)}</ul>}
      </div>
    </InspectorSplit>
  </div>;
}
