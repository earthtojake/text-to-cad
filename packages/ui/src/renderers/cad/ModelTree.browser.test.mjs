import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';

// Render the real shared tree surfaces with a tiny in-memory assembly. Geometry
// inference and viewport picking have separate contract tests; this exercises
// browser layout and scrolling, which jsdom cannot measure.
test('file and model trees share row sizing while model disclosure, isolation and one-shot reveal remain independent', async t => {
  const { outputFiles } = await build({ stdin: {
    resolveDir: fileURLToPath(new URL('.', import.meta.url)), loader: 'jsx', contents: `
import React, { useState } from 'react';
import { createRoot } from 'react-dom/client';
import ModelingTree from '../../../dist/renderers/cad/components/workbench/ModelingTree.js';
import { FileTree } from '../../../dist/file-viewer/navigation/FileTree.js';
const leaves = Array.from({length:70}, (_, i) => ({id:'o'+i,nodeType:'part',displayName:'Part '+i,leafPartIds:['o'+i],children:[]}));
const group = {id:'group',nodeType:'assembly',displayName:'Subassembly',leafPartIds:['o0','o1'],children:leaves.slice(0,2)};
const root = {id:'__step_model__',nodeType:'assembly',displayName:'Document',leafPartIds:leaves.map(n=>n.id),children:[group,...leaves.slice(2)]};
const descriptor = {components:{c:{}},occurrences:leaves.map(n=>({id:n.id,component:'c',name:n.displayName}))};
const baseSource = {rootName:'Files',listings:{'':[{path:'part.step',name:'part.step',kind:'file'}]},load(){},revision:0,paths:async()=>['part.step'],platform:'linux',capabilities:new Set(),onAction(){}};
const events = {selected:[],requested:[]};
function App(){
 const [expanded,setExpanded]=useState([]),[files,setFiles]=useState(new Set()),[selected,setSelected]=useState([]),[hidden,setHidden]=useState([]),[focused,setFocused]=useState([]),[tick,setTick]=useState(0),[reveal,setReveal]=useState(0);
 const toggle=id=>setExpanded(current=>current.includes(id)?current.filter(n=>n!==id):[...current,id]);
 const choose=id=>{events.selected.push(id);setSelected([id]);};
 window.treeTest={events,refresh:()=>setTick(n=>n+1),select:id=>{setSelected([id]);setReveal(n=>n+1);},isolate:()=>{setExpanded(['group']);setFocused(['o0']);}};
 return <div style={{display:'flex',gap:20,padding:16}}>
  <section data-testid="files" style={{height:360,width:280}}><FileTree source={{...baseSource,expanded:files,setExpanded:setFiles}} activePath={null} onOpen={()=>{}}/></section>
  <section data-testid="model" style={{height:360,width:320}}><ModelingTree active disabled={false}
    modeling={{descriptor,results:{},error:'',retryFailed(){}}} stepRoot={root} selectedPartIds={selected}
    activeTreeNodeScrollKey={reveal} onRequestRecognition={ids=>{events.requested=ids;}}
    partControls={{isAssemblyView:true,expandedTreeNodeIds:expanded,onToggleTreeNode:toggle,hiddenPartIds:hidden,
      focusedNodeIds:focused,selectableNodeIds:focused.length?['o0']:null,onSelectTreeNode:choose,
      onTogglePartVisibility:id=>setHidden(current=>current.includes(id)?current.filter(n=>n!==id):[...current,id]),
      showAllHiddenParts:()=>setHidden([]),onExitAllIsolate:()=>setFocused([])}}
    selectionDetails={selected.length?<p>Selected {selected[0]} ({tick})</p>:null}/></section>
 </div>;
}
createRoot(document.getElementById('root')).render(<App/>);
` }, bundle: true, write: false, format: 'esm', platform: 'browser', jsx: 'automatic' });
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  const server = createServer((request, response) => {
    if (request.url === '/app.js') { response.setHeader('content-type', 'text/javascript'); response.end(outputFiles[0].contents); }
    else if (request.url === '/styles.css') { response.setHeader('content-type', 'text/css'); response.end(css); }
    else { response.setHeader('content-type', 'text/html'); response.end('<!doctype html><link rel="stylesheet" href="/styles.css"><div id="root"></div><script type="module" src="/app.js"></script>'); }
  });
  let browser;
  t.after(async () => { await browser?.close(); await new Promise(resolve => server.close(resolve)); });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1000, height: 700 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const model = page.getByTestId('model');
  const part = model.getByRole('button', { name: 'Select Part 2', exact: true });
  await part.waitFor();
  assert.equal(await model.getByRole('button', { name: 'Select Document', exact: true }).count(), 0);
  const modelHeight = (await part.boundingBox()).height;
  const fileHeight = await page.getByTestId('files').locator('[data-path="part.step"]').evaluate(node => node.getBoundingClientRect().height);
  assert.equal(modelHeight, 28);
  assert.equal(modelHeight, fileHeight);
  const beforeHide = await part.boundingBox();
  await model.getByRole('button', { name: 'Hide Part 2', exact: true }).click();
  await model.getByRole('button', { name: 'Show all', exact: true }).waitFor();
  assert.equal((await part.boundingBox()).y, beforeHide.y, 'show/hide must not insert a header row');
  await model.getByRole('button', { name: 'Show all', exact: true }).click();
  await model.getByRole('button', { name: 'Expand Subassembly', exact: true }).click();
  assert.deepEqual(await page.evaluate(() => window.treeTest.events.selected), [], 'disclosure must not select');
  await model.getByRole('button', { name: 'Select Part 0', exact: true }).click();
  assert.deepEqual(await page.evaluate(() => window.treeTest.events.selected), ['o0']);
  assert.equal(await model.getByRole('button', { name: 'Select Part 0', exact: true }).evaluate(node => getComputedStyle(node).fontWeight), '400');
  await page.evaluate(() => window.treeTest.isolate());
  await page.waitForFunction(() => document.querySelector('[aria-label="Select Subassembly"]')?.disabled);
  assert.equal(await model.getByRole('button', { name: 'Select Part 0', exact: true }).isEnabled(), true, 'isolated descendant survives an excluded ancestor');
  assert.equal(await model.getByRole('button', { name: 'Select Part 1', exact: true }).isEnabled(), false);
  await model.getByRole('button', { name: 'Exit isolate', exact: true }).click();
  await page.evaluate(() => window.treeTest.select('o69'));
  const scrollPosition = () => page.evaluate(() => {
    let node = document.querySelector('[aria-label="Model"]');
    while (node && getComputedStyle(node).overflowY !== 'auto') node = node.parentElement;
    return node?.scrollTop;
  });
  await page.waitForFunction(() => {
    let node = document.querySelector('[aria-label="Model"]');
    while (node && getComputedStyle(node).overflowY !== 'auto') node = node.parentElement;
    return node?.scrollTop > 100;
  });
  await page.evaluate(() => {
    let node = document.querySelector('[aria-label="Model"]');
    while (node && getComputedStyle(node).overflowY !== 'auto') node = node.parentElement;
    node.scrollTop = 0;
    window.treeTest.refresh();
  });
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  assert.equal(await scrollPosition(), 0, 'ordinary rerenders must not lock scroll to the selection');
  await model.getByRole('button', { name: 'Collapse Subassembly', exact: true }).click();
  await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  assert.equal(await scrollPosition(), 0, 'other expansion changes must not repeat the reveal');
  assert.deepEqual(errors, []);
});
