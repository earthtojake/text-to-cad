import assert from 'node:assert/strict';
import test from 'node:test';
import { foldRepeatedParts, presentModelingAssembly } from './modelingPresentation.js';

const part=(id,label,component)=>({id:`model:${id}`,kind:'part',label,selectionId:id,leafPartIds:[id],component});
const labels=nodes=>nodes.map(node=>node.label);

test('sibling parts sharing a component fold into one row carrying the count',()=>{
 const folded=foldRepeatedParts([
  part('o1','plant_1_01','c1'),part('o2','plant_1_02','c1'),part('o3','plant_1_03','c1'),
 ],'model:root');
 assert.deepEqual(labels(folded),['plant_1 (3)']);
 assert.deepEqual(labels(folded[0].children),['plant_1_01','plant_1_02','plant_1_03']);
 assert.deepEqual(folded[0].memberSelectionIds,['o1','o2','o3']);
 assert.deepEqual(folded[0].leafPartIds,['o1','o2','o3']);
});

test('the key is the component, so close names with unlike geometry stay apart',()=>{
 const folded=foldRepeatedParts([
  part('o1','column_1_deck_socket','c1'),part('o2','column_1_module_1','c2'),
 ],'model:root');
 assert.deepEqual(labels(folded),['column_1_deck_socket','column_1_module_1']);
});

test('identical names with the same component still fold, and keep that name',()=>{
 const folded=foldRepeatedParts([part('o1','bolt','c1'),part('o2','bolt','c1')],'model:root');
 assert.deepEqual(labels(folded),['bolt (2)']);
});

test('a component used once is left alone',()=>{
 const nodes=[part('o1','plant_1_01','c1'),part('o2','lid','c2')];
 assert.deepEqual(labels(foldRepeatedParts(nodes,'model:root')),['plant_1_01','lid']);
});

test('a row with no component never folds, so a tree without occurrence data is unchanged',()=>{
 const nodes=[part('o1','plate',null),part('o2','plate',undefined)];
 assert.deepEqual(labels(foldRepeatedParts(nodes,'model:root')),['plate','plate']);
});

test('an assembly never folds: collapsing one would hide the structure the tree shows',()=>{
 const assembly=(id,label)=>({id:`model:${id}`,kind:'assembly',label,selectionId:id,component:'c1',children:[]});
 const nodes=[assembly('a1','stage'),assembly('a2','stage')];
 assert.deepEqual(labels(foldRepeatedParts(nodes,'model:root')),['stage','stage']);
});

test('the group sits where its first member sat, so the tree reads in assembly order',()=>{
 const folded=foldRepeatedParts([
  part('o1','hatch_handle','c0'),
  part('o2','plant_1_01','c1'),
  part('o3','spacer','c2'),
  part('o4','plant_1_02','c1'),
 ],'model:root');
 assert.deepEqual(labels(folded),['hatch_handle','plant_1 (2)','spacer']);
});

test('the stem backs up past the digits the common prefix splits',()=>{
 const stem=names=>foldRepeatedParts(names.map((name,at)=>part(`o${at}`,name,'c1')),'model:root')[0].label;
 assert.equal(stem(['plant_1_09','plant_1_10']),'plant_1 (2)');
 assert.equal(stem(['rib-3','rib-4']),'rib (2)');
 assert.equal(stem(['m3 1','m3 2']),'m3 (2)');
});

test('one component under unlike names stays unfolded: the names carry what a count cannot',()=>{
 // A robot's three wheels are one component placed three times. `Left Wheel (3)`
 // would name one of them and lose the other two.
 const wheels=[part('w1','Left Wheel','c1'),part('w2','Right Wheel','c1'),part('w3','Rear Wheel','c1')];
 assert.deepEqual(labels(foldRepeatedParts(wheels,'model:root')),['Left Wheel','Right Wheel','Rear Wheel']);
});

test('parts named only by number stay unfolded, because the number is the whole name',()=>{
 const nodes=[part('o1','01','c1'),part('o2','02','c1')];
 assert.deepEqual(labels(foldRepeatedParts(nodes,'model:root')),['01','02']);
});

test('an assembly read from the STEP tree folds its repeated children',()=>{
 const descriptor={occurrences:[
  {id:'o1',name:'plant',component:'c1'},{id:'o2',name:'plant',component:'c1'},{id:'o3',name:'lid',component:'c2'},
 ]};
 const stepRoot={id:'root',name:'deck',children:[
  {id:'o1',name:'plant_1_01',children:[]},{id:'o2',name:'plant_1_02',children:[]},{id:'o3',name:'lid',children:[]},
 ]};
 const rows=presentModelingAssembly(descriptor,{},stepRoot);
 assert.deepEqual(labels(rows),['plant_1 (2)','lid']);
 assert.deepEqual(rows[0].memberSelectionIds,['o1','o2']);
});
