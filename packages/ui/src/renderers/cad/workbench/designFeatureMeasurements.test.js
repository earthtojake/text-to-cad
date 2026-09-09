import assert from 'node:assert/strict';
import { test } from 'node:test';
import { designFeatureMeasurements as measure } from './designFeatureMeasurements.js';
const face = (id, min, max, area, params) => ({id,selectorType:'face',pickData:{bbox:{min,max},area,params:params ? {radius:params.radius} : undefined,surfaceType:params?.kind}});
test('unions translated bounds and sums unique faces without treating source values as geometry', () => {
 const refs=[face('f1',[1,2,3],[4,6,3],12,{kind:'cylinder',radius:2}),face('f2',[-1,2,3],[1,6,8],20,{kind:'cylinder',radius:2})];
 assert.deepEqual(measure({faceIds:['f1','f2','f1']},refs,[]),{size:[5,4,5],area:32,radii:[2]});
});
test('imported part bounds work without source links, but never imply volume or face area', () => {
 const parts=[{id:'o1',bounds:{min:[-5,2,0],max:[5,8,3]}}];
 assert.deepEqual(measure({partIds:['o1']},[],parts),{size:[10,6,3],area:null,radii:[]});
});
test('missing data does not become zero or a misleading partial total; torus/cone radii are omitted', () => {
 const refs=[face('f1',[0,0,0],[1,1,1],null,{kind:'torus',radius:4}),face('f2',[0,0,0],[1,1,1],1,{kind:'cone',radius:3})];
 assert.deepEqual(measure({faceIds:['f1','missing']},refs,[]),{size:null,area:null,radii:[]});
 assert.deepEqual(measure({faceIds:['f1','f2']},refs,[]),{size:[1,1,1],area:null,radii:[]});
 assert.deepEqual(measure({},refs,[]),{size:null,area:null,radii:[]});
});

test('dimension previews measure placed world-axis extents and reject incomplete or flat spans', async () => {
 const {designFeatureDimension: dimension}=await import('./designFeatureMeasurements.js');
 const refs=[face('f1',[10,-4,2],[16,3,2],42)];
 const x=dimension({faceIds:['f1']},refs,[],0);
 assert.deepEqual(x.pickA.point,[10,-4,2]);
 assert.deepEqual(x.pickB.point,[16,-4,2]);
 assert.equal(x.measurement.euclidean,6);
 assert.equal(dimension({faceIds:['f1']},refs,[],2),null);
 assert.equal(dimension({faceIds:['f1','missing']},refs,[],0),null);
 assert.equal(dimension({partIds:['body']},[],[{id:'body',bounds:{min:[-9,2,0],max:[-4,7,8]}}],2).measurement.euclidean,8);
 assert.equal(dimension({faceIds:['f1']},refs,[],3),null);
});
