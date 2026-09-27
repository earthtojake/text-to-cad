import assert from 'node:assert/strict';
import test from 'node:test';
import {referenceMeasurements} from './referenceMeasurements.js';
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
