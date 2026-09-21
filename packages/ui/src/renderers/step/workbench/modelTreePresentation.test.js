import test from 'node:test';
import assert from 'node:assert/strict';
import {modelTreePresentation,modelTreeReferenceAncestors,modelTreeGroupCopyText} from './modelTreePresentation.js';
const face = id => ({id:`node:${id}`,nodeType:'topology-face',topologyReferenceId:id,displayName:id,children:[]});
const faces=[face('o1.f1'),face('o1.f2')];
const edge={id:'edge',nodeType:'topology-edge',topologyReferenceId:'o1.e1',children:[]};
const refs=[...faces.map((node,i)=>({id:node.topologyReferenceId,selectorType:'face',copyText:`#${node.topologyReferenceId}`,pickData:{surfaceType:i?'cylinder':'plane'}})),{id:'o1.e1',selectorType:'edge',copyText:'#o1.e1'}];
const root={id:'o1',nodeType:'part',children:[{id:'x:folder:faces-edges',nodeType:'topology-folder',children:[...faces,edge]}]};
test('parts show collapsed-capable entity folders with original reference nodes intact',()=>{
 const tree=modelTreePresentation(root,refs);
 assert.deepEqual(tree.children.map(node=>node.displayName),['Faces (2)','Edges (1)']);
 assert.equal(tree.children[0].children[0],faces[0]);
 assert.equal(root.children.length,1);
});
test('surface grouping preserves references and reveals the path for a prompt chip',()=>{
 const tree=modelTreePresentation(root,refs,true);
 assert.deepEqual(tree.children[0].children.map(node=>node.displayName),['Planar (1)','Cylindrical (1)']);
 assert.deepEqual(tree.children[0].children[1].groupReferenceIds,['o1.f2']);
 assert.deepEqual(modelTreeReferenceAncestors(tree,'o1.f2'),['o1','model-group:o1:faces','model-group:o1:surface:cylinder']);
});
test('group copy supports edges and refuses incomplete selections',()=>{
 const map=new Map(refs.map(ref=>[ref.id,ref])),entry={file:'case.step',fileRefPrefix:'case'};
 assert.equal(modelTreeGroupCopyText(['o1.e1'],map,entry),'case#o1.e1');
 assert.equal(modelTreeGroupCopyText(['o1.f1','missing'],map,entry),'');
});
