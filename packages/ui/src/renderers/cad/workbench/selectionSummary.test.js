import assert from 'node:assert/strict';
import test from 'node:test';
import { selectionSummary } from './selectionSummary.js';
const face = (id, occurrenceId) => ({id, occurrenceId, selectorType:'face'});
test('keeps one parent name and deduplicates canonical references', () => {
 const a=face('a','left');
 assert.deepEqual(selectionSummary([a,a,face('b','left')],[{id:'left',name:'Left frame'}]),{label:'2 faces',context:'Left frame'});
});
test('counts repeated part instances separately even if they share a name or component', () => {
 assert.deepEqual(selectionSummary([face('a','left'),face('b','right')],[{id:'left',name:'Frame'},{id:'right',name:'Frame'}]),{label:'2 faces',context:'2 parts'});
});
test('summarizes mixed types without listing names or claiming incomplete parent counts', () => {
 assert.deepEqual(selectionSummary([face('a','left'),{id:'b',selectorType:'edge'}]),{label:'1 face, 1 edge',context:''});
 assert.deepEqual(selectionSummary([{id:'left',name:'Frame',nodeType:'part'},face('a','left')]),{label:'1 face, 1 part',context:''});
 assert.deepEqual(selectionSummary([]),{label:'',context:''});
});

test('omits unnamed instance IDs from the human-readable summary', () => {
 assert.deepEqual(selectionSummary([face('a','o1')],[{id:'o1',name:'o1'}]),{label:'1 face',context:''});
});
