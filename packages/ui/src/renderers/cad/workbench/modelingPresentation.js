import { unique } from './modelingGeometry.js';

const folders = {boss:'Bosses',pocket:'Pockets',hole:'Bores',cut:'Cuts',round:'Edge blends'};

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

// Keep the STEP's assembly hierarchy. Scope every repeated part's operation IDs
// and canonical face/edge references without copying or guessing its source history.
export function presentModelingAssembly(descriptor,results) {
  if(!descriptor)return [];
  const occurrences=new Map(descriptor.occurrences.map(o=>[o.id,o]));
  const scope=(node,occurrenceId)=>({...node,id:`${occurrenceId}/${node.id}`,occurrenceId,children:node.children?.map(n=>scope(n,occurrenceId))});
  const part=o=>{
    const result=results[o.component],tree=result?.tree;
    const bodies=tree ? presentModelingTree(tree) : [];
    const operations=tree?.flatMap(n=>n.children||[]).filter(n=>n.kind!=='remainder') || [];
    const summary=!result?'Recognizing…':result.error?'Unavailable':!tree.length?'No faces':operations.length ? `${operations.length} ${operations.length===1?'feature':'features'}`:'Other geometry';
    const node={id:`part:${o.id}`,kind:'part',label:o.name||'Part',occurrenceId:o.id,faces:tree?.flatMap(n=>n.faces)||[],edges:[],summary,
      note:result?.error || (!tree?.length && result ? 'This component has no faces to inspect.' : undefined),
      children:(bodies.length===1 ? bodies[0].children?.length ? bodies[0].children : bodies : bodies).map(n=>scope(n,o.id)),featureCount:operations.length};
    // A closed leaf still shows its status; it never asks for missing topology.
    return node;
  };
  const visit=n=>{
    const o=occurrences.get(n.id);
    if(o)return part(o);
    const children=(n.children||[]).map(visit).filter(Boolean);
    return children.length?{id:`assembly:${n.id}`,kind:'assembly',label:n.name||'Assembly',faces:[],edges:[],children}:null;
  };
  if(descriptor.occurrences.length===1){
    const o=descriptor.occurrences[0],result=results[o.component];
    return result?.tree ? presentModelingTree(result.tree).map(n=>scope(n,o.id)) : [part(o)];
  }
  const root=descriptor.assembly?.root;
  return root ? [visit(root)].filter(Boolean) : descriptor.occurrences.map(part);
}
