import test from 'node:test';
import assert from 'node:assert/strict';
import { designFeaturePromptText } from './designFeaturePrompt.js';

const entry = {file:'models/case.step',fileRefPrefix:'case'};
const referenceMap = new Map(['f2','f9'].map(id => [id,{id,selectorType:'face',copyText:`#${id}`} ]));
test('a feature becomes one canonical multi-face prompt reference', () => {
  assert.equal(designFeaturePromptText({faceIds:['f9','f2','f9'],partIds:[]},{entry,referenceMap}), 'case#f2,f9');
});
test('repeated parts use occurrence selectors, never their display labels', () => {
  const parts=[{id:'o2',name:'wheel left'},{id:'o3',name:'wheel right'}];
  assert.equal(designFeaturePromptText({partIds:['o3','o2']},{entry,parts}), 'case#o2,o3');
});
test('missing geometry rejects the whole group instead of adding a misleading partial reference', () => {
  assert.equal(designFeaturePromptText({faceIds:['f2','missing']},{entry,referenceMap}), '');
  const malformed = new Map([...referenceMap, ['broken',{id:'broken',selectorType:'face',copyText:'not a selector'}]]);
  assert.equal(designFeaturePromptText({faceIds:['f2','broken']},{entry,referenceMap:malformed}), '');
  assert.equal(designFeaturePromptText({partIds:['o2','o3']},{entry,parts:[{id:'o2'}]}), '');
  assert.equal(designFeaturePromptText({partIds:['source:20']},{entry,parts:[{id:'source:20'}]}), '');
  assert.equal(designFeaturePromptText({faceIds:[],partIds:[]},{entry,referenceMap}), '');
});
