import test from 'node:test';
import assert from 'node:assert/strict';
import { groupDesignFeatures, sourceParameterNode } from './designFeatureTree.js';
import { designFeatureSelection } from './designFeatureSelection.js';

const parts = [{id:'body',name:'Body'}, {id:'wing',name:'Wing'}];
const resolved = {parts:['body','wing'],faces:[],lines:{},partLines:{10:[0],20:[1],30:[1],40:[0,1]}};
const features = [
  {id:'extrude',type:'extrude',line:10,parameters:[{sourceParameters:['WIDTH']}],children:[{id:'sketch',type:'sketch',line:3}]},
  {id:'box',type:'box',line:20}, {id:'fillet',type:'fillet',line:30},
  {id:'repeat',type:'pattern',line:39,sourceParameters:['COUNT'],children:[{id:'shared',line:40}]},
  {id:'unknown',line:50},
];

test('groups uniquely associated operations under parts, keeping repeats and unlinked operations once at assembly level', () => {
  const [group, shared] = groupDesignFeatures(features,resolved,parts);
  assert.deepEqual(group.children.map(part=>part.children.map(child=>child.id)),[['extrude'],['box','fillet']]);
  assert.deepEqual(shared.children.map(child=>child.id),['repeat','unknown']);
  assert.equal(group.children[0].children[0].children[0].id,'sketch');
  assert.deepEqual(designFeatureSelection(group.children[1],resolved).partIds,['wing']);
  assert.deepEqual(designFeatureSelection(group,resolved).partIds,['body','wing']);
  assert.equal(groupDesignFeatures(features,null,parts),features);
  assert.equal(groupDesignFeatures(features,{...resolved,parts:[]},parts),features);
});

test('source parameters preview associated operations and whole repeats; unrelated constants never select the whole model', () => {
  assert.deepEqual(designFeatureSelection(sourceParameterNode({name:'WIDTH'},features),resolved).partIds,['body']);
  assert.deepEqual(designFeatureSelection(sourceParameterNode({name:'COUNT'},features),resolved).partIds,['body','wing']);
  assert.deepEqual(designFeatureSelection(sourceParameterNode({name:'UNKNOWN'},features),resolved).partIds,[]);
});

test('sketch parameter references use the consuming operation, not the helper source line', () => {
  const node=sourceParameterNode({name:'RADIUS'},[{type:'extrude',line:20,children:[{type:'sketch',line:999,parameters:[{sourceParameters:['RADIUS']}]}]}]);
  assert.deepEqual(node.sourceLines,[20]);
  assert.deepEqual(designFeatureSelection(node,resolved).partIds,['wing']);
});
