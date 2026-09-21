import test from 'node:test';
import assert from 'node:assert/strict';
import { buildEdgeChainGraph } from './edgeChainSelection.js';
import { connectedReferenceIds, filterSelectionReferences, toggleReferenceGroupSelection } from './selectionFilter.js';
const edge = (id, a, b, extra = {}) => {
  const direction = b.map((v,i) => v-a[i]), length = Math.hypot(...direction);
  return { id, selectorType:'edge', occurrenceId:'o1', shapeId:'o1.s1', ...extra,
    pickData:{adjacentSelectors:['o1.f1'],chainEndpoints:[{point:a,direction:direction.map(v=>v/length)},{point:b,direction:direction.map(v=>-v/length)}],...extra.pickData} };
};
const chain = (refs, seed='a') => new Set(connectedReferenceIds(buildEdgeChainGraph(refs),seed));
test('selects open chains and closed loops across corners',()=>{
 const refs=[edge('a',[0,0,0],[1,0,0]),edge('b',[1,0,0],[1,1,0]),edge('c',[1,1,0],[0,0,0])];
 assert.deepEqual(chain(refs),new Set(['a','b','c']));
 assert.deepEqual(chain(refs.slice(0,2)),new Set(['a','b']));
 assert.deepEqual(toggleReferenceGroupSelection(['a','b'],['a','b'],true),[]);
 assert.deepEqual(filterSelectionReferences([...refs,{id:'face',selectorType:'face'}],'edge-chain'),refs);
});
test('continues straight through a branch but never floods competing branches',()=>{
 const a=edge('a',[0,0,0],[1,0,0]), b=edge('b',[1,0,0],[2,0,0]), c=edge('c',[1,0,0],[1,1,0]);
 assert.deepEqual(chain([a,b,c]),new Set(['a','b']));
 assert.deepEqual(chain([a,b,c],'c'),new Set(['c']));
 assert.deepEqual(chain([a,b,c,edge('d',[1,0,0],[3,0,0])]),new Set(['a']));
});
test('does not join nearby disconnected faces, solids or occurrences; unknown endpoints stay individual',()=>{
 const a=edge('a',[0,0,0],[1,0,0]);
 for(const extra of [{shapeId:'o1.s2'},{occurrenceId:'o2'},{partId:'other'},{pickData:{adjacentSelectors:['o1.f2']}},{pickData:{chainEndpoints:[]}}])
  assert.deepEqual(chain([a,edge('b',[1,0,0],[2,0,0],extra)]),new Set(['a']));
});
