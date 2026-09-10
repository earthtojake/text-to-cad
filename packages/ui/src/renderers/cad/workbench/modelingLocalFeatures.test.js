import assert from 'node:assert/strict';
import test from 'node:test';
import fs from 'node:fs';
import { buildModelingTree } from './modelingTree.js';
import { boreFeatures } from './modelingBores.js';
import { localPrismaticFeatures } from './modelingLocalFeatures.js';
import { presentModelingTree, presentModelingAssembly } from './modelingPresentation.js';
const fixture=name=>JSON.parse(fs.readFileSync(new URL(`./__tests__/fixtures/${name}.json`,import.meta.url)));
const maps=i=>[i.faces,new Map(i.faces.map(f=>[f.ord,f])),new Map(i.edges.map(e=>[e.ord,e]))];

test('local inference identifies the imported pocket and boss independently of full reconstruction',()=>{
 const index=fixture('externalPocketBoss'),features=localPrismaticFeatures(...maps(index));
 assert.deepEqual(features.map(n=>n.kind),['boss','pocket']);
 const boss=features[0],pocket=features[1];
 assert.deepEqual(boss.faces,[12,13]);assert.ok(Math.abs(boss.measurements[0][1]-80)<1e-4);
 assert.deepEqual(pocket.faces,[15,16,17,18,19,20,21,22,23]);assert.ok(Math.abs(pocket.measurements[0][1]-5)<1e-4);
 assert.equal(pocket.children[0].edges.length,8);
});
test('a missing rim, altered wall, or unproven direction leaves a pocket unrecognized',()=>{
 for(const change of [i=>{i.edges.find(e=>e.ord===1).length+=1;},i=>{i.faces.find(f=>f.ord===15).normal=[0,0,1];},i=>{i.faces.find(f=>f.ord===19).normal=[0,1,0];}]){
  const i=fixture('externalPocketBoss');change(i);assert.equal(localPrismaticFeatures(...maps(i)).filter(n=>n.kind==='pocket').length,0);
 }
});
test('a real external split cylindrical wall becomes one bore with both canonical faces',()=>{
 const i=fixture('externalSplitBore'),features=boreFeatures(...maps(i));
 assert.equal(features.length,1);assert.deepEqual(features[0].faces,[87,88]);
 assert.ok(Math.abs(features[0].measurements[0][1]-1)<1e-4);
 for(const change of [i=>{i.faces.find(f=>f.ord===87).reversed=!i.faces.find(f=>f.ord===87).reversed;},i=>{i.edges.find(e=>e.curve?.kind==='circle').length*=0.5;}]){
  const copy=fixture('externalSplitBore');change(copy);assert.equal(boreFeatures(...maps(copy)).length,0);
 }
});

// Analytic controls: two cylindrical stages joined by an annular shoulder, or
// one cylindrical stage ending in a conical countersink. No source parsing.
function steppedBore(conical=false) {
 const frame={origin:[0,0,0],xdir:[1,0,0],ydir:[0,1,0],zdir:[0,0,1]};
 const edge=(ord,r,z,faceOrds)=>({ord,shape:1,faceOrds,length:2*Math.PI*r,curveType:'circle',params:{radius:r},curve:{...frame,kind:'circle',origin:[0,0,z],radius:r,range:[0,2*Math.PI]}});
 const edges=[edge(1,2,0,[1,90]),edge(2,2,5,[1,3]),edge(3,4,conical?8:5,[conical?3:2,conical?91:3])];
 if(!conical)edges.push(edge(4,4,8,[2,91]));
 const cylinder=(ord,r,z,depth,ids)=>({ord,shape:1,surfaceType:'cylinder',reversed:true,uv:[0,2*Math.PI,0,depth],surface:{...frame,kind:'cylinder',radius:r,origin:[0,0,z]},params:{origin:[0,0,z],axis:[0,0,1],radius:r},area:2*Math.PI*r*depth,loops:[ids.map(edgeOrd=>({edgeOrd}))]});
 const face={ord:3,shape:1,surfaceType:conical?'cone':'plane',reversed:true,normal:[0,0,1],uv:[0,2*Math.PI,0,Math.sqrt(13)],surface:{...frame,origin:[0,0,5],kind:conical?'cone':'plane',radius:2,semiAngle:Math.atan2(2,3)},area:Math.PI*12,loops:[[{edgeOrd:2}],[{edgeOrd:3}]]};
 const faces=[cylinder(1,2,0,5,[1,2]),face];if(!conical)faces.push(cylinder(2,4,5,3,[3,4]));
 for(const ord of [90,91])faces.push({ord,shape:1,surfaceType:'plane',normal:[0,0,1],area:1000,loops:[]});
 return {faces,edges};
}
test('counterbores and countersinks are connected stages, not unrelated surface rows',()=>{
 for(const conical of [false,true]){
  const i=steppedBore(conical),features=boreFeatures(...maps(i));assert.equal(features.length,1);
  assert.equal(features[0].label,conical?'Countersunk bore':'Counterbore');
  assert.deepEqual(features[0].faces,conical?[1,3]:[1,2,3]);
 }
});
test('material boundaries inside a proposed bore prevent a false empty-hole feature',()=>{
 const i=steppedBore();
 i.edges.push({ord:99,shape:1,length:1,faceOrds:[99],curve:{kind:'line',origin:[0,0,2],dir:[1,0,0],range:[0,1]}});
 i.faces.push({ord:99,shape:1,surfaceType:'plane',normal:[0,0,1],area:1,loops:[[{edgeOrd:99}]]});
 const features=boreFeatures(...maps(i));
 assert.ok(features.every(n=>!n.faces.includes(1)));assert.ok(features.every(n=>n.label!=='Counterbore'));
});
test('folders preserve each operation and face reference without naming a pattern',()=>{
 const operations=Array.from({length:8},(_,i)=>({id:`p${i}`,kind:'pocket',label:`Pocket ${i+1}`,faces:[i+1],edges:[]}));
 const input=[{id:'body:1',children:operations,faces:operations.flatMap(n=>n.faces)}];
 const [result]=presentModelingTree(input);assert.equal(result.children.length,1);assert.equal(result.children[0].label,'Pockets (8)');
 assert.deepEqual(result.children[0].children,operations);assert.deepEqual(result.children[0].faces,[1,2,3,4,5,6,7,8]);assert.equal(input[0].children.length,8);
});
test('annotation-only STEP components do not produce unselectable body rows',()=>{
 assert.deepEqual(buildModelingTree({faces:[],edges:[],shapes:[{ord:1,kind:'shape'}]}),[]);
});
 test('a rejected bore cannot reappear through the generic cut fallback',()=>{
  const i=fixture('annular');
  i.edges.push({ord:99,shape:1,length:1,faceOrds:[99],curve:{kind:'line',origin:[-61,42.6,16],dir:[1,0,0],range:[0,1]}});
  i.faces.push({ord:99,shape:1,surfaceType:'plane',normal:[1,0,0],center:[-60.5,42.6,16],area:1,loops:[[{edgeOrd:99}]]});
  const [body]=buildModelingTree(i);
  assert.equal(body.complete,false);
  assert.ok(body.children.find(n=>n.kind==='remainder').faces.includes(4));
  assert.ok(body.children.every(n=>!['hole','cut'].includes(n.kind)));
 });

test('assembly presentation preserves nesting and scopes reused component features',()=>{
 const operations=[{id:'body:1',kind:'body',faces:[1],children:[{id:'extrude:1',kind:'extrude',label:'Base extrude',faces:[1],edges:[]}]}];
 const descriptor={components:{c:{}},occurrences:[{id:'o1.1',component:'c',name:'Left'},{id:'o1.2',component:'c',name:'Right'}],assembly:{root:{id:'o1',name:'Wheels',children:[{id:'o1.1'},{id:'o1.2'}]}}};
 const [assembly]=presentModelingAssembly(descriptor,{c:{tree:operations}});
 assert.equal(assembly.label,'Wheels');assert.deepEqual(assembly.children.map(n=>n.label),['Left','Right']);
 const [left,right]=assembly.children.map(n=>n.children[0]);
 assert.notEqual(left.id,right.id);assert.equal(right.occurrenceId,'o1.2');assert.deepEqual(right.faces,[1]);assert.equal(operations[0].id,'body:1');
 assert.equal(presentModelingAssembly(descriptor,{} )[0].children[0].summary,'Recognizing…');
});
