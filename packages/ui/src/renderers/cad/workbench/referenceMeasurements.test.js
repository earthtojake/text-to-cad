import assert from 'node:assert/strict';
import test from 'node:test';
import {referenceMeasurements,selectionMeasurements} from './referenceMeasurements.js';
const edge=(id,kind,params={},length=null,center=[0,0,0])=>({id,selectorType:'edge',pickData:{curveType:kind,params,length,center}});
const face=(id,kind,params={},area=null,normal=null)=>({id,selectorType:'face',pickData:{surfaceType:kind,params,area,normal,center:params.origin}});
const row=(rows,label)=>rows.find(r=>r[0]===label)?.[1];
test('circular dimensions use radius and analytic sweep, not a polyline length',()=>{
 const q=referenceMeasurements(edge('a','circle',{radius:5,sweepRadians:Math.PI/2},7.8));
 assert.equal(q.kind,'arc');assert.equal(row(q.rows,'Diameter Ø'),10);assert.equal(row(q.rows,'Sweep angle'),90);
 assert.equal(row(q.rows,'Arc length'),5*Math.PI/2);
 const circle=referenceMeasurements(edge('a','circle',{radius:5,sweepRadians:2*Math.PI},31.4));
 assert.equal(row(circle.rows,'Circumference'),10*Math.PI);assert.equal(row(circle.rows,'Sweep angle'),undefined);
});
test('legacy circular edges keep radius without inventing a sweep; noncircular surfaces do not get a generic diameter',()=>{
 const q=referenceMeasurements(edge('a','circle',{radius:5},31.4));assert.equal(row(q.rows,'Sweep angle'),undefined);
 assert.equal(row(referenceMeasurements(face('t','torus',{majorRadius:8,minorRadius:2})).rows,'Diameter Ø'),undefined);
 assert.equal(row(referenceMeasurements(face('c','cylinder',{radius:4})).rows,'Diameter Ø'),8);
 assert.deepEqual(referenceMeasurements(edge('a','line',{},null)).rows,[]);
});
test('selection totals deduplicate references and never present a partial total as complete',()=>{
 const a=edge('a','line',{},3),b=edge('b','line',{},4);
 assert.equal(row(selectionMeasurements([a,a,b]),'Total length'),7);
 assert.equal(row(selectionMeasurements([a,edge('b','line')]),'Total length'),undefined);
 assert.equal(row(selectionMeasurements([face('a','plane',{},10),face('b','plane',{},20)]),'Total area'),30);
});
test('circle spacing uses analytic centers, not sampled edge centroids',()=>{
 const a=edge('a','circle',{radius:2,center:[0,0,0]},12,[2,0,0]);
 const b=edge('b','circle',{radius:4,center:[3,4,0]},25,[7,4,0]);
 assert.equal(row(selectionMeasurements([a,b]),'Center distance'),5);
});
test('plane spacing and acute angles use model-space normals and retain coplanar zero',()=>{
 const a=face('a','plane',{origin:[0,0,0]},10,[0,0,1]);
 assert.equal(row(selectionMeasurements([a,face('b','plane',{origin:[20,30,5]},10,[0,0,-1])]),'Plane spacing'),5);
 assert.equal(row(selectionMeasurements([a,face('b','plane',{origin:[20,30,0]},10,[0,0,-1])]),'Plane spacing'),0);
 assert.equal(row(selectionMeasurements([a,face('b','plane',{origin:[0,0,0]},10,[1,0,0])]),'Angle'),90);
});
test('parallel cylinder axis spacing ignores arbitrary axial origins',()=>{
 const a=face('a','cylinder',{origin:[0,0,100],axis:[0,0,1],radius:2});
 const b=face('b','cylinder',{origin:[3,4,-200],axis:[0,0,-1],radius:3});
 assert.equal(row(selectionMeasurements([a,b]),'Axis spacing'),5);
});
test('straight edges report acute angle or supporting-line spacing; unsupported pairs get no guessed gap',()=>{
 const a=edge('a','line',{origin:[0,0,0],direction:[1,0,0]},3);
 assert.equal(row(selectionMeasurements([a,edge('b','line',{origin:[0,0,0],direction:[0,1,0]},4)]),'Angle'),90);
 assert.equal(row(selectionMeasurements([a,edge('b','line',{origin:[100,4,0],direction:[-1,0,0]},4)]),'Line spacing'),4);
 assert.deepEqual(selectionMeasurements([face('a','bspline'),edge('b','bspline')]),[]);
});
