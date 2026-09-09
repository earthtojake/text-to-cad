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

test('imported parts and grouped faces keep the full filename and native selectors', () => {
  const entry = {file:'models/Hex Drive Screw (2).STEP', fileRefPrefix:'Hex Drive Screw (2).STEP'};
  const parts = [{id:'o1'}, {id:'o2',name:'same label'}, {id:'o3',name:'same label'}];
  assert.equal(designFeaturePromptText({partIds:['o3','o1','o2']},{entry,parts}), '"Hex Drive Screw (2).STEP"#o1,o2,o3');
  const referenceMap = new Map(['o1.f2','o1.f3'].map(id => [id,{id,selectorType:'face',copyText:`"Hex Drive Screw (2).STEP"#${id} surface info`}]));
  assert.equal(designFeaturePromptText({faceIds:['o1.f3','o1.f2']},{entry,referenceMap}), '"Hex Drive Screw (2).STEP"#o1.f2,o1.f3');
});

test('keeps feature context to one source pointer and the selected measurement', async () => {
  const {designFeatureContextText}=await import('./designFeaturePrompt.js');
  const context={file:'models/case.step',source:'models/case.py',line:20,label:'Profile · Rounded rectangle',parameters:[{name:'width',value:30,expression:'WIDTH'}],measurements:{size:[30,20,0],area:600,radii:[]},inspection:{kind:'axis',value:0}};
  const text=designFeatureContextText(context);
  assert.equal(text,'Profile · Rounded rectangle · X extent = 30 mm · models/case.step · models/case.py:20');
  assert.doesNotMatch(text,/\n|Source inputs|Measured face area|#source:/);
  assert.doesNotMatch(designFeatureContextText(context,{includeModel:false}),/models\/case.step/);
  assert.equal(designFeatureContextText({file:'part.step',label:'Imported geometry'},{includeModel:false}),'');
  assert.match(designFeatureContextText({...context,inspection:null}),/width = 30/);
});
