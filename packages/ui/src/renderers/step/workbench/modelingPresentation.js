import { stepTreeNodeIsTopology, stepTreeNodeLeafPartIds, stepTreeNodeLabel } from '@text-to-cad/core/lib/step/stepTree.js';

// Structural wrappers add no choice when there is only one. Keep them in the
// logical tree (and the host's expansion frontier), but show their children.
// Never flatten a folded group: its disclosure is the person's.
export function implicitModelingRoots(tree) {
  const roots=[];
  let nodes=tree;
  while(nodes.length === 1 && nodes[0].kind === 'assembly' && nodes[0].children?.length) {
    roots.push(nodes[0]);
    nodes=nodes[0].children;
  }
  return roots;
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
      leafPartIds:[...new Set(members.flatMap(member=>member.leafPartIds || []))],
      // What the row selects and hides: the instances themselves, never a synthetic
      // id of its own, which no part of the host knows about.
      memberSelectionIds:members.map(member=>member.selectionId).filter(Boolean),
      children:members,
    });
  }
  return folded;
}

// The STEP's assembly hierarchy as the tree's rows: an assembly over its children, and a part
// a leaf, its faces and edges never rows (they are the viewport's to pick). A part names its
// component (`componentId`, once its mesh is in), which is what folds repeated parts.
export function presentModelingAssembly(stepRoot) {
  if(!stepRoot)return [];
  const fromStep=n=>{
    if(stepTreeNodeIsTopology(n))return null;
    const children=(n.children||[]).map(fromStep).filter(Boolean);
    return {
      id:`model:${n.id}`,selectionId:n.id,leafPartIds:stepTreeNodeLeafPartIds(n),
      kind:children.length ? 'assembly' : 'part',label:stepTreeNodeLabel(n),
      component:n.componentId ?? null,
      children:foldRepeatedParts(children,`model:${n.id}`),
    };
  };
  const root=fromStep(stepRoot);
  // The document's assembly wrapper is already implicitly expanded by picking.
  // Show its children directly, retaining their canonical identities and nesting.
  return root.kind === 'assembly' ? root.children : [root];
}
