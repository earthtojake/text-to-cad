import assert from 'node:assert/strict';
import test from 'node:test';
import { filterSelectionReferences, toggleReferenceGroupSelection } from './selectionFilter.js';
const refs = [{id:'f1',selectorType:'face'}, {id:'f2',selectorType:'face'}, {id:'e1',selectorType:'edge'}];
test('strict filters exclude other entity types', () => {
  assert.deepEqual(filterSelectionReferences(refs,'faces').map(r=>r.id),['f1','f2']);
  assert.deepEqual(filterSelectionReferences(refs,'tangent-faces').map(r=>r.id),['f1','f2']);
  assert.deepEqual(filterSelectionReferences(refs,'edges').map(r=>r.id),['e1']);
  assert.deepEqual(filterSelectionReferences(refs,'parts'),[]);
  assert.equal(filterSelectionReferences(refs,'all'),refs);
});
test('shift restores a saved face reference and toggles it off only when all members are selected', () => {
  assert.deepEqual(toggleReferenceGroupSelection(['f1'],['f2','f3'],true),['f1','f2','f3']);
  assert.deepEqual(toggleReferenceGroupSelection(['f1','f2'],['f2','f3'],true),['f1','f2','f3']);
  assert.deepEqual(toggleReferenceGroupSelection(['f1','f2','f3'],['f2','f3'],true),['f1']);
  assert.deepEqual(toggleReferenceGroupSelection(['f1'],['f2','f3']),['f2','f3']);
});
