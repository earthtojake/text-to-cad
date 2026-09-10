import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react';
import { Box, Boxes, Circle, ChevronRight, CornerUpRight, Layers, RotateCw, Shapes, Spline, SquareDashed } from 'lucide-react';
import { cn } from '@hardcore/ui/utils';
import InspectorSplit from './InspectorSplit.jsx';
import { modelingReferenceIds } from '../../workbench/modelingTree.js';
import { presentModelingAssembly } from '../../workbench/modelingPresentation.js';

const ReconstructionPreview = lazy(() => import('./ReconstructionPreview.jsx'));
const EMPTY = [];
const icons = {part:Box,assembly:Boxes,group:Boxes,boss:Layers,pocket:Shapes,hole:Circle,body:Box,extrude:Layers,loft:Layers,cut:Shapes,revolve:RotateCw,round:CornerUpRight,profile:SquareDashed,curve:Spline,remainder:Box};
const number = n => n.toLocaleString(undefined,{maximumFractionDigits:3});

function ModelingRow({ node, depth=0, selected, expanded, toggle, choose, disabled }) {
  const Icon = icons[node.kind] || Box, open = expanded.has(node.id), branch = node.children?.length > 0;
  return <li className="min-w-0">
    <div className={cn('flex min-w-0 items-center rounded hover:bg-sidebar-accent/50', selected === node.id && 'bg-sidebar-accent')} style={{paddingLeft:depth*14}}>
      {branch ? <button type="button" aria-label={`${open ? 'Collapse' : 'Expand'} ${node.label}`} aria-expanded={open} className="grid size-7 shrink-0 place-items-center rounded text-muted-foreground hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring" onClick={()=>toggle(node.id)}><ChevronRight className={cn('size-3.5 transition-transform',open && 'rotate-90')}/></button> : <span className="w-7 shrink-0"/>}
      <button type="button" aria-label={`Select ${node.label}`} aria-pressed={selected === node.id} disabled={disabled || !(node.faces?.length || node.edges?.length)} onClick={()=>choose(node)} title={node.note || node.label} className="flex h-8 min-w-0 flex-1 items-center gap-2 rounded pr-2 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring disabled:opacity-40">
        <Icon className="size-3.5 shrink-0 text-muted-foreground"/><span className="min-w-0 flex-1 truncate">{node.label}</span>
        {node.summary && <span className="shrink-0 text-micro text-muted-foreground">{node.summary}</span>}
        {node.measurements?.[0] && ['extrude','loft','cut','round','boss','pocket','hole'].includes(node.kind) && <span className="shrink-0 text-micro tabular-nums text-muted-foreground">{node.kind === 'round' ? 'R ' : node.kind === 'hole' ? 'Ø ' : ''}{number(node.measurements[0][1])}</span>}
      </button>
    </div>
    {branch && open && <ul>{node.children.map(child=><ModelingRow key={child.id} {...{node:child,depth:depth+1,selected,expanded,toggle,choose,disabled}}/>)}</ul>}
  </li>;
}

/** Read-only geometry inference; assembly instances share recognition, never selection IDs. */
export default function ModelingTree({ modeling, active, entry, disabled, references=EMPTY, selectedReferenceIds=EMPTY, selectedPartIds=EMPTY, reconstructionEnabled=false, onLoadTopology, onSelect }) {
  const {descriptor,results,error,retryFailed,target,statuses,retryVerification}=modeling;
  const [preview,setPreview]=useState(null);
  const [selected,setSelected]=useState(null),[pending,setPending]=useState(null),[expanded,setExpanded]=useState(new Set());
  const initialExpansion=useRef(false),firstFeatureExpanded=useRef(false);
  const tree=useMemo(()=>presentModelingAssembly(descriptor,results),[descriptor,results]);
  const componentIds=useMemo(()=>[...new Set(descriptor?.occurrences.map(o=>o.component)||[])],[descriptor]);
  const selectionOccurrences=[...new Set(references.filter(r=>selectedReferenceIds.includes(r.id)).map(r=>r.occurrenceId).filter(Boolean))];
  const partId=selectionOccurrences.length===1 ? selectionOccurrences[0] : selectedPartIds.length===1 ? selectedPartIds[0] : selected?.occurrenceId;
  const currentPart=descriptor?.occurrences.find(o=>o.id===partId) || (descriptor?.occurrences.length===1 ? descriptor.occurrences[0] : null);
  const recipe=currentPart && results[currentPart.component]?.recipe;
  const verification=currentPart && statuses[currentPart.component];
  const ready=Object.values(statuses).filter(s=>s.state==='ready').length;
  const emptyComponents=componentIds.filter(id=>results[id]?.hasFaces===false).length;
  const geometryComponents=componentIds.length-emptyComponents;
  useEffect(()=>{if(!active)setPreview(null);},[active]);
  useEffect(()=>{
    if(!partId)return;
    const find=nodes=>{for(const node of nodes){if(node.occurrenceId===partId)return [node.id];const path=find(node.children||[]);if(path)return [node.id,...path];}return null;};
    const path=find(tree);
    if(path)setExpanded(current=>path.every(id=>current.has(id)) ? current : new Set([...current,...path]));
  },[partId,tree]);
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
  useEffect(()=>{
    if(!pending || !active || disabled)return;
    const ids=modelingReferenceIds(pending,pending.occurrenceId,references);
    if(ids.length){onSelect?.(ids);setPending(null);}
  },[pending,active,disabled,references,onSelect]);
  const choose=node=>{
    setSelected(node);setPending(null);
    const ids=modelingReferenceIds(node,node.occurrenceId,references);
    if(ids.length)onSelect?.(ids);
    else if(node.faces?.length || node.edges?.length){setPending(node);onLoadTopology?.([node.occurrenceId]);}
  };
  const ids=selected ? modelingReferenceIds(selected,selected.occurrenceId,references) : EMPTY;
  const selection=new Set(selectedReferenceIds),showDetails=selected && (pending || ids.some(id=>selection.has(id)));
  const empty=descriptor && done===componentIds.length && !failed && componentIds.every(id=>!results[id]?.tree?.length);
  return <div className="flex h-full min-h-0 flex-col text-xs" aria-label="Modeling tree">
    <div className="space-y-2 border-b border-sidebar-border/60 p-2">
      <div className="flex justify-between gap-2 text-micro text-muted-foreground"><span className="truncate" title={currentPart?.name}>{currentPart?.name || 'Features'}</span><span title="Inferred from STEP geometry, not original history.">Inferred · read-only</span></div>
      {loading && <p role="status" className="text-micro text-muted-foreground">{descriptor ? `Recognizing geometry · ${done} of ${componentIds.length} components` : 'Loading model geometry…'}</p>}
      {(error || failed>0) && <p role="alert" className="text-micro text-muted-foreground">{error || `${failed} ${failed===1?'component is':'components are'} unavailable.`} <button type="button" className="underline" onClick={retryFailed}>Retry</button></p>}
      {!loading && !error && !empty && <p className="text-micro text-muted-foreground">Inferred features · original build order unknown.</p>}
      {reconstructionEnabled && componentIds.length>0 && <p role="status" className="text-micro text-muted-foreground">{ready} of {geometryComponents} components reconstructed{Object.values(statuses).some(s=>s.state==='checking') ? ' · Verifying…' : ''}{emptyComponents>0 && <span title="These STEP entries contain no faces."> · {emptyComponents} empty {emptyComponents===1 ? 'entry' : 'entries'}</span>}</p>}
    </div>
    {currentPart && <div className="shrink-0 border-b border-sidebar-border/60 p-2">
      {recipe && reconstructionEnabled ? verification?.state==='ready' ? <button type="button" onClick={()=>setPreview({component:currentPart.component,recipe,label:currentPart.name || 'Part'})} className="flex w-full items-center justify-center gap-2 rounded border px-2 py-1.5 text-xs hover:bg-sidebar-accent"><RotateCw className="size-3.5"/>Play build sequence</button> : verification?.state==='failed' ? <div className="space-y-1 text-micro text-muted-foreground"><p>{verification.error}</p><button type="button" className="underline" onClick={()=>retryVerification(currentPart.component)}>Retry verification</button></div> : <p role="status" className="text-micro text-muted-foreground">{verification?.state==='checking' ? 'Verifying build sequence…' : 'Build sequence queued…'}</p> : <p className="text-micro text-muted-foreground">{recipe ? 'Complete recipe inferred.' : 'Partial recognition · no complete build sequence yet.'}</p>}
    </div>}
    {preview && <Suspense fallback={<p role="status" className="p-2 text-xs">Opening reconstruction…</p>}><ReconstructionPreview {...preview} target={target} file={entry.file} onClose={()=>setPreview(null)}/></Suspense>}
    <InspectorSplit title={selected?.label} label="Modeling details" details={showDetails && <div className="space-y-3 p-3" aria-label="Modeling details">
      {!!selected.measurements?.length && <dl className="space-y-2">{selected.measurements.map(([label,value,unit])=><div key={label} className="flex flex-wrap justify-between gap-x-3 gap-y-1"><dt className="text-muted-foreground">{label}</dt><dd className="tabular-nums">{number(value)} {unit}</dd></div>)}</dl>}
      {selected.note && <p className="text-micro leading-relaxed text-muted-foreground">{selected.note}</p>}
      <div className="text-micro text-muted-foreground">{selected.edges?.length ? `${selected.edges.length} boundary ${selected.edges.length===1?'edge':'edges'}` : `${selected.faces.length} associated faces`}</div>
      {pending && <p role="status" className="text-micro text-muted-foreground">Loading selectable geometry…</p>}
    </div>}>
      <div className="min-h-0 flex-1 overflow-auto p-1">
        {empty ? <p role="status" className="p-2 leading-relaxed text-muted-foreground">This component has no faces to inspect.</p> : <ul aria-label="Inferred modeling operations">{tree.map(node=><ModelingRow key={node.id} {...{node,selected:showDetails ? selected.id : null,expanded,choose,disabled}} toggle={id=>setExpanded(current=>{const next=new Set(current);if(next.has(id))next.delete(id);else next.add(id);return next;})}/>)}</ul>}
      </div>
    </InspectorSplit>
  </div>;
}
