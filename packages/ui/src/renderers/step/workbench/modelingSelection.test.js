import assert from 'node:assert/strict';
import test from 'node:test';
import { modelingSelectionPaths } from './modelingSelection.js';
const descriptor={occurrences:[{id:'o1',component:'c'},{id:'o2',component:'c'}]};
const part=id=>({id,kind:'part',selectionId:id,occurrenceId:id,children:[
  {id:`${id}/base`,kind:'extrude',occurrenceId:id,faces:[1,2],children:[{edges:[1,2]}]},
  {id:`${id}/cut`,kind:'cut',occurrenceId:id,faces:[3,4],children:[{edges:[2,3]}]},
]});
const tree=[part('o1'),part('o2')];
const match=(type,n,occurrence='o1')=>modelingSelectionPaths(tree,[{selectorType:type,normalizedSelector:`${occurrence}.${type[0]}${n}`,occurrenceId:occurrence}],[],descriptor,{c:{edgeFaces:{4:[3,4],5:[1,3]}}}).map(p=>p.at(-1).id);
test('viewport picks match features only within the picked occurrence',()=>{
 assert.deepEqual(match('face',3,'o2'),['o2/cut']);
 assert.deepEqual(match('face',99),['o1']);
});
test('edges use boundary or adjacency links and ambiguous edges keep their parent part',()=>{
 assert.deepEqual(match('edge',1),['o1/base']);
 assert.deepEqual(match('edge',2),['o1']);
 assert.deepEqual(match('edge',4),['o1/cut']);
 assert.deepEqual(match('edge',5),['o1']);
});
test('part selection prefers the exact part over an assembly containing that part',()=>{
 const assembly=[{id:'root',kind:'assembly',leafPartIds:['o1','o2'],children:tree}];
 assert.equal(modelingSelectionPaths(assembly,[],['o2'],descriptor)[0].at(-1).id,'o2');
});
