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
