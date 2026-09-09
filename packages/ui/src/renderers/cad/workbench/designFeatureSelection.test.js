import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveDesignFeatureLinks, designFeatureSelection } from './designFeatureSelection.js';
const face = (x=0) => ({area:10,center:[x,0,0],bbox:{min:[x,-1,-1],max:[x,1,1]}});
const links = {schema:1,faces:[face(0),face(3)],lines:{'10':[0],'20':[1]}};
const references=[{id:'f9',selectorType:'face',pickData:face(3)},{id:'f2',selectorType:'face',pickData:face(0)}];
test('links follow geometry, not reordered face ids; repeat rows combine child operations',()=>{
 const resolved=resolveDesignFeatureLinks(links,references);
 assert.deepEqual(designFeatureSelection({line:10,type:'extrude'},resolved).faceIds,['f2']);
 assert.deepEqual(designFeatureSelection({type:'pattern',children:[{line:10},{line:20}]},resolved).faceIds,['f2','f9']);
 assert.deepEqual(designFeatureSelection({type:'sketch',line:2},resolved,20).faceIds,['f9']);
 assert.deepEqual(designFeatureSelection({type:'parameters'},resolved),{faceIds:[],partIds:[]});
});
test('incomplete, duplicate, and changed geometry cannot be highlighted',()=>{
 assert.equal(resolveDesignFeatureLinks(links,references.slice(1)),null);
 assert.equal(resolveDesignFeatureLinks({...links,faces:[face(0),face(0)]},references),null);
 assert.equal(resolveDesignFeatureLinks(links,[references[0],{...references[1],pickData:face(0.1)}]),null);
});
test('assembly links require both authored names and placed bounds',()=>{
 const parts=[{id:'o2',name:'wing',bounds:face(3).bbox},{id:'o1',name:'body',bounds:face(0).bbox}];
 const assembly={schema:1,parts:[{name:'body',bbox:face(0).bbox},{name:'wing',bbox:face(3).bbox}],partLines:{'30':[1]}};
 assert.deepEqual(designFeatureSelection({line:30},resolveDesignFeatureLinks(assembly,[],parts)).partIds,['o2']);
 assert.equal(resolveDesignFeatureLinks(assembly,[],[{...parts[0],name:'roof'},parts[1]]),null);
});

test('trimmed assembly meshes may fit inside conservative BREP bounds but never outside',()=>{
 const assembly={schema:1,parts:[{name:'body',bbox:{min:[-10,-10,-10],max:[10,10,10]}}],partLines:{'1':[0]}};
 assert.ok(resolveDesignFeatureLinks(assembly,[],[{id:'o1',name:'body',bounds:{min:[-10,-9.5,-10],max:[10,9.5,10]}}]));
 assert.equal(resolveDesignFeatureLinks(assembly,[],[{id:'o1',name:'body',bounds:{min:[-10,-9.5,-10],max:[10,10.5,10]}}]),null);
});
