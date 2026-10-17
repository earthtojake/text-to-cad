import assert from 'node:assert/strict';
import test from 'node:test';
import {createFaceAreas} from './faceAreas.js';

// The measure request a view would send for a face: the face's ordinal, under one view.
const requestFor = reference => ({tree: 't', viewId: 'v', producer: {}, cid: 'c', part: 'p', face: reference.pickData.ordinal});
const face = ordinal => ({id: `o:1a2b3c4d5e6f/f:base.extrude1.${ordinal}`, selectorType: 'face', pickData: {ordinal}});
const settled = () => new Promise(resolve => setTimeout(resolve, 0));

test('a face is measured once, when first asked for, and reads as coming until cadgen answers', async () => {
  const asked = [];
  const areas = createFaceAreas({requestFor, measure: async body => { asked.push(body.face); return {face: body.face, area: 12.5, center: [0, 0, 0]}; }});
  let heard = 0;
  areas.subscribe(() => { heard += 1; });
  assert.deepEqual(areas.peek(face(2)), {state: 'none'}, 'nothing is asked by looking');
  assert.deepEqual(areas.read(face(2)), {state: 'pending'});
  areas.request(face(2));
  await settled();
  assert.deepEqual(areas.peek(face(2)), {state: 'ready', area: 12.5});
  assert.deepEqual(asked, [2], 'one request, however often the face is asked for');
  assert.equal(heard, 2, 'the view hears when it is asked and when it is answered');
});

test('nothing is asked for an edge, a face no view names, or one cadgen cannot measure', async () => {
  const asked = [];
  const areas = createFaceAreas({
    requestFor: reference => (reference.pickData.ordinal === 9 ? null : requestFor(reference)),
    measure: async body => { asked.push(body.face); throw new Error('the component has 3 faces, not a face 4'); },
  });
  assert.deepEqual(areas.read({selectorType: 'edge', pickData: {ordinal: 1}}), {state: 'none'});
  assert.deepEqual(areas.read(face(9)), {state: 'none'});
  areas.request(face(4));
  await settled();
  assert.deepEqual(areas.peek(face(4)), {state: 'failed'});
  assert.deepEqual(asked, [4]);
});
