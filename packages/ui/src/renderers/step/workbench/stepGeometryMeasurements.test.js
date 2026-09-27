import assert from 'node:assert/strict';
import { test } from 'node:test';
import { stepGeometryMeasurements as measure } from './stepGeometryMeasurements.js';
const face = (id, min, max) => ({id,selectorType:'face',pickData:{bbox:{min,max}}});
test('unions translated bounds of unique faces', () => {
 const refs=[face('f1',[1,2,3],[4,6,3]),face('f2',[-1,2,3],[1,6,8])];
 assert.deepEqual(measure({faceIds:['f1','f2','f1']},refs,[]),{size:[5,4,5]});
});
test('imported part bounds work without source links', () => {
 const parts=[{id:'o1',bounds:{min:[-5,2,0],max:[5,8,3]}}];
 assert.deepEqual(measure({partIds:['o1']},[],parts),{size:[10,6,3]});
});
test('missing data does not become zero or a misleading partial size', () => {
 const refs=[face('f1',[0,0,0],[1,1,1]),face('f2',[0,0,0],[1,1,1])];
 assert.deepEqual(measure({faceIds:['f1','missing']},refs,[]),{size:null});
 assert.deepEqual(measure({faceIds:['f1','f2']},refs,[]),{size:[1,1,1]});
 assert.deepEqual(measure({},refs,[]),{size:null});
});
