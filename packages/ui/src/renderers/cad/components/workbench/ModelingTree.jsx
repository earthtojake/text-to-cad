import { useEffect, useMemo, useRef, useState } from 'react';
import { Box, Boxes, Circle, ChevronRight, CornerUpRight, Layers, RotateCw, Shapes, Spline, SquareDashed, X } from 'lucide-react';
import { Button } from '@hardcore/ui/primitives/button';
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

function ModelingRow({ node, depth=0, selected, expanded, toggle, choose, disabled, partControls, rowRefs, inheritedBlocked=false }) {
  const Icon = icons[node.kind] || Box, open = expanded.has(node.id), children = (node.children || []).filter(child => child.kind !== 'curve'), branch = children.length > 0;
  const hidden = node.leafPartIds?.length > 0 && node.leafPartIds.every(id => partControls.hiddenPartIds?.includes(id));
  const unavailable = inheritedBlocked || hidden || (node.selectionId && partControls.selectableNodeIds && !partControls.selectableNodeIds.includes(node.selectionId));
  return <li className="min-w-0" ref={element => { if (element) rowRefs.current.set(node.id, element); else rowRefs.current.delete(node.id); }}>
    <ModelPartMenu node={node} controls={partControls} disabled={disabled} selectDisabled={disabled || unavailable} selected={selected.has(node.id)} onSelect={event=>choose(node,event)}>
    <div className={cn('flex min-w-0 items-center rounded hover:bg-sidebar-accent/50', selected.has(node.id) && 'bg-sidebar-accent', hidden && 'opacity-50')} onMouseEnter={() => partControls.onHoverTreeNode?.(node.selectionId || node.occurrenceId || '')} onMouseLeave={() => partControls.onHoverTreeNode?.('')} style={{paddingLeft:depth*14}}>
      {branch ? <button type="button" aria-label={`${open ? 'Collapse' : 'Expand'} ${node.label}`} aria-expanded={open} className="grid size-7 shrink-0 place-items-center rounded text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring" onClick={()=>toggle(node.id)}><ChevronRight className={cn('size-3.5 transition-transform',open && 'rotate-90')}/></button> : <span className="w-7 shrink-0"/>}
      <button type="button" aria-label={`Select ${node.label}`} aria-pressed={selected.has(node.id)} disabled={disabled || unavailable || !(node.selectionId || node.faces?.length || node.edges?.length)} onClick={event=>choose(node,event)} title={node.label} className="flex h-8 min-w-0 flex-1 items-center gap-2 rounded pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40">
        <Icon className="size-3.5 shrink-0 text-muted-foreground"/><span className="min-w-0 flex-1 truncate">{node.label}</span>
        {node.summary && <span className="shrink-0 text-micro text-muted-foreground">{node.summary}</span>}
        {node.measurements?.[0] && ['extrude','loft','cut','round','boss','pocket','hole'].includes(node.kind) && <span className="shrink-0 text-micro tabular-nums text-muted-foreground">{node.kind === 'round' ? 'R ' : node.kind === 'hole' ? 'Ø ' : ''}{number(node.measurements[0][1])}</span>}
      </button>
      {node.selectionId && <ModelPartActions node={node} controls={partControls} disabled={disabled}/>}
    </div>
    </ModelPartMenu>
    {branch && open && <ul>{children.map(child=><ModelingRow key={child.id} {...{node:child,depth:depth+1,inheritedBlocked:unavailable,selected,expanded,toggle,choose,disabled,partControls,rowRefs}}/>)}</ul>}
  </li>;
}

/** Read-only geometry inference; assembly instances share recognition, never selection IDs. */
export default function ModelingTree({ modeling, active, disabled, references=EMPTY, selectedReferenceIds=EMPTY, selectedPartIds=EMPTY, onLoadTopology, onSelect, onClearSelection, stepRoot, selectedReferences, selectionDetails, activeTreeNodeScrollKey, partControls={} }) {
  const {descriptor,results,error,retryFailed}=modeling;
  const [selected,setSelected]=useState(null),[pending,setPending]=useState(null),[expanded,setExpanded]=useState(new Set());
  const initialExpansion=useRef(false),firstFeatureExpanded=useRef(false);
  const tree=useMemo(()=>presentModelingAssembly(descriptor,results,stepRoot),[descriptor,results,stepRoot]);
  const componentIds=useMemo(()=>[...new Set(descriptor?.occurrences.map(o=>o.component)||[])],[descriptor]);
  const rowRefs=useRef(new Map());
  const picked=useMemo(()=>selectedReferences || references.filter(ref=>selectedReferenceIds.includes(ref.id)),[selectedReferences,references,selectedReferenceIds]);
  const summary=selectionSummary(picked,descriptor?.occurrences);
  const paths=useMemo(()=>modelingSelectionPaths(tree,picked,selectedPartIds,descriptor,results),[tree,picked,selectedPartIds,descriptor,results]);
  useEffect(()=>{
    const ancestors=paths.flatMap(path=>(path.at(-1)?.kind === 'part' ? path : path.slice(0,-1)).map(node=>node.id));
    setExpanded(current=>ancestors.every(id=>current.has(id)) ? current : new Set([...current,...ancestors]));
  },[paths]);
  useEffect(()=>{
    if(active) rowRefs.current.get(paths.at(-1)?.at(-1)?.id)?.scrollIntoView?.({block:'nearest'});
  },[active,paths,expanded,activeTreeNodeScrollKey]);
  const done=componentIds.filter(id=>results[id]).length,loading=!error && (!descriptor || done<componentIds.length);
  const failed=componentIds.filter(id=>results[id]?.error).length;
  useEffect(()=>{
    if(!tree.length)return;
    if(!initialExpansion.current){
      initialExpansion.current=true;
      setExpanded(current=>new Set([...current,...tree.filter(n=>n.kind!=='part').map(n=>n.id)]));
    }
    if(!firstFeatureExpanded.current){
      const find=nodes=>{for(const n of nodes){if(n.kind==='part' && n.featureCount)return [n.id];const child=find(n.children||[]);if(child)return [n.id,...child];}return null;};
      const path=find(tree);
      if(path){firstFeatureExpanded.current=true;setExpanded(current=>new Set([...current,...path]));}
      // Single-part imports replace their initial status row when recognition finishes.
      if(descriptor?.occurrences.length===1 && tree[0].kind==='body'){
        firstFeatureExpanded.current=true;setExpanded(current=>new Set([...current,tree[0].id]));
      }
    }
  },[tree,descriptor]);
  useEffect(()=>{if(!active || disabled)setPending(null);},[active,disabled]);
  const selectionKey=JSON.stringify([selectedReferenceIds,selectedPartIds]);
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
      onLoadTopology?.([node.selectionId]);
      return;
    }
    setSelected(node);setPending(null);
    const ids=modelingReferenceIds(node,node.occurrenceId,references);
    if(ids.length)onSelect?.(ids);
    else if(node.faces?.length || node.edges?.length){setPending({...node,selectionKey});onLoadTopology?.([node.occurrenceId]);}
  };
  const ids=selected ? modelingReferenceIds(selected,selected.occurrenceId,references) : EMPTY;
  const selection=new Set(selectedReferenceIds),showDetails=selected && (pending || (ids.length > 0 && ids.length === selection.size && ids.every(id=>selection.has(id))));
  const highlighted=new Set(showDetails ? [selected.id] : paths.map(path=>path.at(-1).id));
  const empty=descriptor && done===componentIds.length && !failed && componentIds.every(id=>!results[id]?.tree?.length);
  return <div className="flex h-full min-h-0 flex-col text-xs" aria-label="Modeling tree">
    {(loading || error || failed>0) && <div className="space-y-2 border-b border-sidebar-border/60 p-2">
      {loading && <p role="status" className="text-micro text-muted-foreground">{descriptor ? `Recognizing geometry · ${done} of ${componentIds.length} components` : 'Loading model geometry…'}</p>}
      {(error || failed>0) && <p role="alert" className="text-micro text-muted-foreground">{error || `${failed} ${failed===1?'component is':'components are'} unavailable.`} <button type="button" className="underline" onClick={retryFailed}>Retry</button></p>}
    </div>}
    {(partControls.hiddenPartIds?.length > 0 || partControls.focusedNodeIds?.length > 0) && <div className="flex shrink-0 gap-3 border-b border-sidebar-border/60 px-3 py-2 text-micro">
      {partControls.hiddenPartIds?.length > 0 && <button disabled={disabled} type="button" className="text-muted-foreground hover:text-foreground" onClick={partControls.showAllHiddenParts}>Show all</button>}
      {partControls.focusedNodeIds?.length > 0 && <button disabled={disabled} type="button" className="text-muted-foreground hover:text-foreground" onClick={partControls.onExitAllIsolate}>Exit isolate</button>}
    </div>}
    <InspectorSplit title={summary.label ? <span className="flex min-w-0 items-center gap-1">
      <span className="max-w-full shrink-0 truncate">{summary.label}</span>
      {summary.context && <span className="truncate text-muted-foreground">· {summary.context}</span>}
    </span> : showDetails ? selected?.label : 'Selection'}
    titleTooltip={summary.label ? [summary.label,summary.context].filter(Boolean).join(' · ') : undefined}
    actions={summary.label && onClearSelection ? <Button type="button" variant="ghost" size="icon-xs" aria-label="Clear selection" title="Clear selection" disabled={disabled} onClick={()=>{setSelected(null);setPending(null);onClearSelection();}}><X className="size-3.5" aria-hidden="true"/></Button> : null}
    label="Modeling details" details={showDetails && selected.edges?.length === 1 && !pending && selectionDetails ? selectionDetails : showDetails ? (selected.measurements?.length || pending ? <div className="space-y-3 p-3" aria-label="Modeling details">
      {!!selected.measurements?.length && <dl className="space-y-2">{selected.measurements.map(([label,value,unit])=><div key={label} className="flex flex-wrap justify-between gap-x-3 gap-y-1"><dt className="text-muted-foreground">{label}</dt><dd className="tabular-nums">{number(value)} {unit}</dd></div>)}</dl>}
      {pending && <p role="status" className="text-micro text-muted-foreground">Loading selectable geometry…</p>}
    </div> : selectionDetails) : selectionDetails}>
      <div className="min-h-0 flex-1 overflow-auto p-1">
        {empty && !stepRoot ? <p role="status" className="p-2 leading-relaxed text-muted-foreground">This component has no faces to inspect.</p> : <ul aria-label="Model">{tree.map(node=><ModelingRow key={node.id} {...{node,selected:highlighted,expanded,choose,disabled,partControls,rowRefs}} toggle={id=>setExpanded(current=>{const next=new Set(current);if(next.has(id))next.delete(id);else next.add(id);return next;})}/>)}</ul>}
      </div>
    </InspectorSplit>
  </div>;
}
