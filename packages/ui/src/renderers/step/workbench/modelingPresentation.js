import { STEP_MODEL_ROOT_ID, stepTreeNodeIsTopology, stepTreeNodeLeafPartIds, stepTreeNodeLabel } from '@hardcore/core/lib/step/stepTree.js';
import { unique } from './modelingGeometry.js';

const folders = {boss:'Bosses',pocket:'Pockets',hole:'Bores',cut:'Cuts',round:'Edge blends'};

// Structural wrappers add no choice when there is only one. Keep them in the
// logical tree (and the host's expansion frontier), but show their children.
// Never flatten a feature/group: its disclosure controls face/edge selection.
export function implicitModelingRoots(tree) {
  const roots=[];
  let nodes=tree;
  while(nodes.length === 1 && ['assembly','part','body'].includes(nodes[0].kind)
    && (nodes[0].children?.length || nodes[0].recognitionPending)) {
    roots.push(nodes[0]);
    nodes=nodes[0].children || [];
  }
  return roots;
}

// Presentation grouping only. Repeated geometry is not evidence of a CAD pattern.
export function presentModelingTree(tree) {
  return tree.map(body=>{
    const grouped = new Map();
    for(const child of body.children || []){
      if(!grouped.has(child.kind))grouped.set(child.kind,[]);
      grouped.get(child.kind).push(child);
    }
    const seen = new Set(), children = [];
    for(const child of body.children || []){
      const group = grouped.get(child.kind);
      if(folders[child.kind] && group.length>5){
        if(seen.has(child.kind))continue;
        seen.add(child.kind);
        children.push({id:`${body.id}:group:${child.kind}`,kind:'group',label:`${folders[child.kind]} (${group.length})`,faces:unique(group.flatMap(n=>n.faces)),edges:[],children:group,
          note:'Grouped for inspection; no pattern operation or build order is implied.'});
      } else children.push(child);
    }
    return {...body,children};
  });
}

// The name a folded row can honestly carry: the stem its members share, backed up
// past the digits the common prefix splits, so plant_1_01..plant_1_06 reads
// `plant_1 (6)` rather than `plant_1_0 (6)`.
//
// Empty means there is no such name, and that is a REASON NOT TO FOLD rather than
// a cue to borrow one. A robot's Left, Right and Rear Wheel are one component
// placed three times; folding them under `Left Wheel (3)` would name one instance,
// count three, and throw away the only thing telling them apart. Parts named
// purely by number (`01`, `02`) come out empty for the same reason: the number is
// all the name there is.
function repeatedLabelStem(labels) {
  let stem=labels[0] || '';
  for(const label of labels.slice(1)){
    let at=0;
    while(at < stem.length && at < label.length && stem[at] === label[at])at+=1;
    stem=stem.slice(0,at);
  }
  return stem.replace(/[\s._-]*\d*$/,'');
}

// An assembly repeats itself: a tray of six identical planters is six rows that
// say nothing about being six of one thing. Sibling parts that share a COMPONENT
// **and a name** fold into one row carrying the count, every instance still under it.
//
// Both halves are load-bearing, and in opposite directions. The component -- the
// occurrence's geometry, hashed from its source -- is what makes the fold true, so
// two unlike parts a CAD author happened to number _01 and _02 are never merged on
// the strength of their names. The shared name is what makes it READABLE: same
// component, unlike names means the names carry what the count cannot, and those
// rows stay apart (see repeatedLabelStem).
//
// A row with no component never folds, and neither does an assembly: collapsing one
// would hide the structure the tree exists to show. The group sits where its first
// member sat, so the tree still reads in assembly order.
export function foldRepeatedParts(nodes,ownerId) {
  const repeats=new Map();
  for(const node of nodes){
    if(node.kind !== 'part' || !node.component)continue;
    repeats.set(node.component,(repeats.get(node.component) || 0)+1);
  }
  const folded=[],seen=new Set();
  for(const node of nodes){
    const component=node.kind === 'part' ? node.component : null;
    if(!component || repeats.get(component) < 2){folded.push(node);continue;}
    if(seen.has(component))continue;
    seen.add(component);
    const members=nodes.filter(other=>other.kind === 'part' && other.component === component);
    const stem=repeatedLabelStem(members.map(member=>member.label));
    if(!stem){for(const member of members)folded.push(member);continue;}
    folded.push({
      id:`${ownerId}:repeat:${component}`,kind:'group',
      label:`${stem} (${members.length})`,
      faces:[],edges:[],
      leafPartIds:unique(members.flatMap(member=>member.leafPartIds || [])),
      // What the row selects and hides: the instances themselves, never a synthetic
      // id of its own, which no part of the host knows about.
      memberSelectionIds:members.map(member=>member.selectionId).filter(Boolean),
      children:members,
      note:'One row for a component the assembly repeats; no pattern operation is implied.',
    });
  }
  return folded;
}

// Keep the STEP's assembly hierarchy. Scope every repeated part's operation IDs
// and canonical face/edge references without copying or guessing its source history.
export function presentModelingAssembly(descriptor,results,stepRoot=null) {
  if(!descriptor && !stepRoot)return [];
  const occurrences=new Map((descriptor?.occurrences||[]).map(o=>[o.id,o]));
  const scope=(node,occurrenceId)=>({...node,id:`${occurrenceId}/${node.id}`,occurrenceId,children:node.children?.map(n=>scope(n,occurrenceId))});
  const part=o=>{
    const result=results[o.component],tree=result?.tree;
    const bodies=tree ? presentModelingTree(tree) : [];
    const operations=tree?.flatMap(n=>n.children||[]).filter(n=>n.kind!=='remainder') || [];
    const summary=!result?'':result.error?'Unavailable':!tree.length?'No faces':operations.length ? `${operations.length} ${operations.length===1?'feature':'features'}`:'Other geometry';
    const node={id:`part:${o.id}`,kind:'part',label:o.name||'Part',occurrenceId:o.id,faces:tree?.flatMap(n=>n.faces)||[],edges:[],summary,
      note:result?.error || (!tree?.length && result ? 'This component has no faces to inspect.' : undefined),
      children:(bodies.length===1 ? bodies[0].children?.length ? bodies[0].children : bodies : bodies).map(n=>scope(n,o.id)),featureCount:operations.length,
      recognitionPending:!result};
    // Unknown geometry still has a disclosure; only opening it requests recognition.
    return node;
  };
  const visit=n=>{
    const o=occurrences.get(n.id);
    if(o)return part(o);
    const children=(n.children||[]).map(visit).filter(Boolean);
    return children.length?{id:`assembly:${n.id}`,kind:'assembly',label:n.name||'Assembly',faces:[],edges:[],children}:null;
  };
  if(stepRoot){
    const fromStep=n=>{
      if(stepTreeNodeIsTopology(n))return null;
      const children=(n.children||[]).map(fromStep).filter(Boolean);
      const occurrence=occurrences.get(n.id) || (n.id===STEP_MODEL_ROOT_ID && descriptor?.occurrences.length===1 ? descriptor.occurrences[0] : null);
      const recognized=occurrence ? part(occurrence) : null;
      return {
        ...(recognized || {faces:[],edges:[]}),
        id:`model:${n.id}`,selectionId:n.id,leafPartIds:stepTreeNodeLeafPartIds(n),
        kind:children.length && !occurrence ? 'assembly':'part',label:stepTreeNodeLabel(n),
        // The geometry key the fold below groups on, carried from the occurrence.
        component:occurrence?.component ?? null,
        children:recognized?.children || foldRepeatedParts(children,`model:${n.id}`),
      };
    };
    const root=fromStep(stepRoot);
    // The document's assembly wrapper is already implicitly expanded by picking.
    // Show its children directly, retaining their canonical identities and nesting.
    return root?.kind === 'assembly' && root.children.length ? root.children : [root].filter(Boolean);
  }
  if(descriptor.occurrences.length===1){
    const o=descriptor.occurrences[0],result=results[o.component];
    return result?.tree ? presentModelingTree(result.tree).map(n=>scope(n,o.id)) : [part(o)];
  }
  const root=descriptor.assembly?.root;
  return root ? [visit(root)].filter(Boolean) : descriptor.occurrences.map(part);
}
