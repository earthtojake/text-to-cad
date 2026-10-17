import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import { createServer } from 'node:http';
import { build } from 'esbuild';
import { chromium } from 'playwright';

// The real model tree, over an in-memory assembly: browser layout and scrolling, which jsdom
// cannot measure. Viewport picking has separate contract tests.
//
// A large assembly, every row open: the tree mounts only the rows in view (and a margin), yet
// lays out exactly as the whole tree would — the same total height, every row where it would
// sit — and a pick, a search cursor and the parts on screen under Faces all work through it.
test('a tree of thousands of rows mounts only the rows in view, laid out as the whole tree; reveal, search, re-renders and topology requests hold; and under Faces or Edges a large tree asks for the part the pointer rests on or presses', async t => {
  const GROUPS = 30, PARTS = 100;
  const { outputFiles } = await build({ stdin: {
    resolveDir: fileURLToPath(new URL('.', import.meta.url)), loader: 'jsx', contents: `
import React, { useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import ModelingTree from '../../../dist/renderers/step/components/workbench/ModelingTree.js';
import { createHoverStore } from '../../../dist/renderers/step/workbench/hoverStore.js';
// ?groups=&parts= size the assembly; the default is ${GROUPS} groups of ${PARTS} parts.
const query = new URLSearchParams(location.search);
const GROUPS = +query.get('groups') || ${GROUPS}, PARTS = +query.get('parts') || ${PARTS};
const groups = Array.from({length:GROUPS}, (_, g) => {
  const parts = Array.from({length:PARTS}, (_, i) => ({id:'o'+g+'_'+i,nodeType:'part',displayName:'Part '+g+'-'+i,leafPartIds:['o'+g+'_'+i],children:[]}));
  return {id:'g'+g,nodeType:'assembly',displayName:'Group '+g,leafPartIds:parts.map(p=>p.id),children:parts};
});
const leaves = groups.flatMap(g=>g.children);
const root = {id:'__step_model__',nodeType:'assembly',displayName:'Document',leafPartIds:leaves.map(n=>n.id),children:groups};
const events = {selected:[],topology:[]};
const hoverStore = createHoverStore();
window.treeTest = {events, hoverStore, order:groups.flatMap(g=>['Group '+g.id.slice(1), ...g.children.map(p=>p.displayName)])};
const face = (id, n) => ({id:id+'.f'+n,selectorType:'face',occurrenceId:id,normalizedSelector:id+'.f'+n});
function App(){
  const [selected,setSelected]=useState([]),[reveal,setReveal]=useState(0),[mode,setMode]=useState('all'),[tick,setTick]=useState(0),[loading,setLoading]=useState(false),[picked,setPicked]=useState([]);
  const expanded=useMemo(()=>groups.map(g=>g.id),[]);
  const partControls=useMemo(()=>({isAssemblyView:true,expandedTreeNodeIds:expanded,onToggleTreeNode(){},hiddenPartIds:[],focusedNodeIds:[],selectableNodeIds:null,
    onSelectTreeNode:id=>{events.selected.push(id);setSelected([id]);},menuForNode:id=>({nodeId:id,copyText:id,zoomSelectionAvailable:false})}),[expanded]);
  const onLoadTopology=useMemo(()=>ids=>{events.topology.push(...ids);},[]);
  Object.assign(window.treeTest,{refresh:()=>setTick(n=>n+1),loading:()=>setLoading(value=>!value),select:id=>{setPicked([]);setSelected([id]);setReveal(n=>n+1);},setMode,
    // What a face picked in the viewport hands the tree: that face, as the selected reference.
    pickFace:(id,n)=>{setSelected([]);setPicked([face(id,n)]);setReveal(k=>k+1);}});
  // As the viewer holds it: the tool stack beside the viewport's canvas, in one surface.
  return <div data-cad-surface="" style={{display:'flex'}}>
    <canvas data-testid="viewport" width="200" height="200" style={{width:200,height:200}}/>
    <section data-testid="model" data-tick={tick} style={{height:420,width:320,display:'flex',flexDirection:'column',gap:8,padding:16}}>
      <ModelingTree active disabled={false} mode={mode} stepRoot={root} selectedPartIds={selected} selectedReferences={picked}
        activeTreeNodeScrollKey={reveal} onLoadTopology={onLoadTopology} partControls={partControls} loading={loading} hoverStore={hoverStore}/>
    </section>
  </div>;
}
createRoot(document.getElementById('root')).render(<App/>);
` }, bundle: true, write: false, format: 'esm', platform: 'browser', jsx: 'automatic' });
  const css = await readFile(new URL('../../../dist/styles.css', import.meta.url));
  // Counts the renders of every row component, through React's own devtools hook.
  const hook = `<script>(() => {
    const counts = { ModelingRow: 0, ModelingSearchRow: 0, ModelingTree: 0 };
    window.__renders = counts;
    const nameOf = f => (f.type && (f.type.displayName || f.type.name)) || '';
    window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = { supportsFiber: true, renderers: new Map(), inject() { return 1; }, checkDCE() {}, onScheduleFiberRoot() {},
      onCommitFiberUnmount() {}, onPostCommitFiberRoot() {}, setStrictMode() {},
      onCommitFiberRoot(_id, root) { const stack = [root.current];
        while (stack.length) { const f = stack.pop(); if (typeof f.type === 'function') { const n = nameOf(f);
          if (n in counts && (!f.alternate || f.alternate.memoizedProps !== f.memoizedProps)) counts[n]++; }
          if (f.child) stack.push(f.child); if (f.sibling) stack.push(f.sibling); } } };
  })();</script>`;
  const server = createServer((request, response) => {
    if (request.url === '/app.js') { response.setHeader('content-type', 'text/javascript'); response.end(outputFiles[0].contents); }
    else if (request.url === '/styles.css') { response.setHeader('content-type', 'text/css'); response.end(css); }
    else { response.setHeader('content-type', 'text/html'); response.end(`<!doctype html><link rel="stylesheet" href="/styles.css">${hook}<div id="root"></div><script type="module" src="/app.js"></script>`); }
  });
  let browser;
  t.after(async () => { await browser?.close(); await new Promise(resolve => server.close(resolve)); });
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve); });
  browser = await chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 800, height: 700 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(`http://127.0.0.1:${server.address().port}`);
  const model = page.getByTestId('model');
  await model.getByRole('button', { name: 'Select Part 0-0', exact: true }).waitFor();
  const frames = () => page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
  const order = await page.evaluate(() => window.treeTest.order);
  assert.equal(order.length, GROUPS * (PARTS + 1));
  // Where every mounted row is, against where the whole tree would put it: its place in the
  // tree order times the row height, and at that row's indent.
  const layout = () => page.evaluate(() => {
    const list = document.querySelector('[aria-label="Model"]'), scroller = list.closest('[data-tool-panel-body]');
    const top = list.getBoundingClientRect().top;
    return { listHeight: list.getBoundingClientRect().height, scrollHeight: scroller.scrollHeight, clientHeight: scroller.clientHeight, scrollTop: scroller.scrollTop,
      rows: [...list.querySelectorAll(':scope > li')].map(li => ({ label: li.querySelector('button[aria-pressed]').getAttribute('aria-label').replace(/^Select /, ''),
        top: li.getBoundingClientRect().top - top, height: li.getBoundingClientRect().height, level: li.getAttribute('aria-level') })) };
  });
  const check = (state, where) => {
    assert.equal(state.listHeight, order.length * 24, `${where}: the list is every row tall`);
    // The panel body holds the list and its 4px padding above and below: nothing else.
    assert.equal(state.scrollHeight, order.length * 24 + 8, `${where}: the scroll range is the whole tree's`);
    assert.ok(state.rows.length > 0 && state.rows.length <= 60, `${where}: ${state.rows.length} rows mounted`);
    for (const row of state.rows) {
      const at = order.indexOf(row.label);
      assert.equal(row.top, at * 24, `${where}: ${row.label} sits where the whole tree puts it`);
      assert.equal(row.height, 24);
      assert.equal(row.level, row.label.startsWith('Group') ? '1' : '2');
    }
    // What is on screen is mounted, contiguously.
    const first = Math.floor(state.scrollTop / 24), last = Math.min(order.length - 1, Math.floor((state.scrollTop + state.clientHeight) / 24));
    const mounted = new Set(state.rows.map(row => row.label));
    for (let at = first; at <= last; at += 1) assert.ok(mounted.has(order[at]), `${where}: ${order[at]} is on screen and mounted`);
  };
  check(await layout(), 'top');
  const indent = await model.getByRole('button', { name: 'Select Part 0-1', exact: true })
    .evaluate(node => [node.parentElement.style.paddingLeft, node.parentElement.querySelectorAll('[data-tree-guide]').length]);
  // The row's 5px inset (TREE_ROW_INSET_PX) and one compact 10px level.
  assert.deepEqual(indent, ['15px', 1], 'a part under its group is one compact level in, hung from its group\'s line');
  for (const fraction of [0.37, 0.5, 0.999, 0.02]) {
    await page.evaluate(fraction => { const scroller = document.querySelector('[aria-label="Model"]').closest('[data-tool-panel-body]'); scroller.scrollTop = (scroller.scrollHeight - scroller.clientHeight) * fraction; }, fraction);
    await frames();
    check(await layout(), `scrolled to ${fraction}`);
  }

  // A parent re-rendered with the same props renders nothing; one that changes only the filter row's status
  // renders the tree, but not one row.
  await frames();
  const before = await page.evaluate(() => ({ ...window.__renders }));
  assert.ok(before.ModelingRow > 0 && before.ModelingTree > 0, `the counts see the rows and the tree: ${JSON.stringify(before)}`);
  await page.evaluate(() => window.treeTest.refresh()); await frames();
  const same = await page.evaluate(() => ({ ...window.__renders }));
  assert.deepEqual([same.ModelingTree - before.ModelingTree, same.ModelingRow - before.ModelingRow], [0, 0], 'unchanged props: no tree or row render');
  await page.evaluate(() => window.treeTest.loading()); await frames();
  const detailed = await page.evaluate(() => ({ ...window.__renders }));
  assert.ok(detailed.ModelingTree > same.ModelingTree, 'the tree rendered for its status');
  assert.equal(detailed.ModelingRow - same.ModelingRow, 0, 'and no row did');
  await page.evaluate(() => window.treeTest.loading()); await frames();

  // A row holding focus, and a row holding its menu open, stay mounted while the list scrolls
  // far away from them.
  const scrollTo = fraction => page.evaluate(fraction => { const scroller = document.querySelector('[aria-label="Model"]').closest('[data-tool-panel-body]'); scroller.scrollTop = (scroller.scrollHeight - scroller.clientHeight) * fraction; }, fraction);
  await scrollTo(0); await frames();
  await model.getByRole('button', { name: 'Select Part 0-5', exact: true }).focus();
  await scrollTo(1); await frames();
  assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('aria-label')), 'Select Part 0-5', 'focus stays on its row');
  assert.equal(await page.evaluate(() => document.activeElement?.isConnected), true);
  await scrollTo(0); await frames();
  await model.getByRole('button', { name: 'Select Part 0-3', exact: true }).click({ button: 'right' });
  const menu = page.getByRole('menu');
  await menu.waitFor();
  await scrollTo(1); await frames();
  assert.equal(await model.locator('li[data-virtual-row="model:o0_3"]').count(), 1, 'the row whose menu is open stays mounted');
  assert.equal(await menu.isVisible(), true, 'and its menu open');
  await page.keyboard.press('Escape');
  await menu.waitFor({ state: 'detached' });
  check(await layout(), 'after the menu');

  // A pick far down the tree scrolls its row into view.
  await page.evaluate(() => { document.querySelector('[aria-label="Model"]').closest('[data-tool-panel-body]').scrollTop = 0; });
  await frames();
  await page.evaluate(() => window.treeTest.select('o27_93'));
  await page.waitForFunction(() => {
    const row = document.querySelector('[aria-label="Select Part 27-93"]'), scroller = document.querySelector('[aria-label="Model"]')?.closest('[data-tool-panel-body]');
    if (!row || !scroller) return false;
    const box = row.getBoundingClientRect(), view = scroller.getBoundingClientRect();
    return box.top >= view.top - 1 && box.bottom <= view.bottom + 1;
  });
  assert.equal(await model.getByRole('button', { name: 'Select Part 27-93', exact: true }).getAttribute('aria-pressed'), 'true');
  await frames();
  check(await layout(), 'revealed');

  // Search: two hundred ranked hits in the same rows; the cursor walks them from the keyboard,
  // each step in view, and Enter selects the hit under it.
  const search = model.getByRole('textbox', { name: 'Filter model' });
  await search.fill('part 1');
  const results = model.locator('[aria-label="Model search results"]');
  await results.waitFor();
  const hits = await results.evaluate(list => ({ height: list.getBoundingClientRect().height, mounted: list.querySelectorAll(':scope > li').length }));
  assert.equal(hits.height, 200 * 24, 'every hit is a row of the list');
  assert.ok(hits.mounted <= 60, `${hits.mounted} hits mounted`);
  await search.focus();
  for (let step = 0; step < 45; step += 1) await page.keyboard.press('ArrowDown');
  await frames();
  const cursor = await results.evaluate(list => {
    const rows = [...list.querySelectorAll(':scope > li')];
    const row = rows.find(li => li.firstElementChild?.classList.contains('bg-accent/30'));
    const scroller = list.closest('[data-tool-panel-body]'), box = row.getBoundingClientRect(), view = scroller.getBoundingClientRect();
    return { id: row.dataset.searchRow, top: box.top - list.getBoundingClientRect().top, visible: box.top >= view.top - 1 && box.bottom <= view.bottom + 1 };
  });
  assert.equal(cursor.top, 45 * 24, 'the cursor is the 46th hit');
  assert.ok(cursor.visible, 'and it is in view');
  await page.keyboard.press('Enter');
  assert.equal(`model:${(await page.evaluate(() => window.treeTest.events.selected)).at(-1)}`, cursor.id, 'Enter selects the hit under the cursor');
  await search.fill('');
  await model.locator('[aria-label="Model"]').waitFor();

  // A large tree (more than LARGE_TREE_ROWS rows of assemblies and parts) under Faces: its
  // assemblies stay open and locked, its parts are leaves, and nothing asks for topology for being
  // on screen.
  const topology = () => page.evaluate(() => [...window.treeTest.events.topology]);
  await scrollTo(0);
  await page.evaluate(() => { window.treeTest.events.topology.length = 0; window.treeTest.setMode('faces'); });
  await model.locator('[data-disclosure-locked]').first().waitFor();
  await frames();
  assert.equal(await model.locator('[aria-label="Model"]').evaluate(list => list.getBoundingClientRect().height), order.length * 24, 'the rows are the assemblies and parts');
  assert.deepEqual(await model.locator('[data-disclosure-locked]').evaluateAll(marks => [...new Set(marks.map(mark => mark.dataset.disclosureLocked))]), ['open'], 'only the assemblies are locked, open');
  assert.equal(await model.getByRole('button', { name: /^(Expand|Collapse) Part / }).count(), 0, 'a part has no disclosure');
  await scrollTo(0.5); await frames(); await scrollTo(0); await frames();
  assert.deepEqual(await topology(), [], 'parts on screen ask for nothing');
  // A face picked in the viewport scrolls the tree to its part's row, far down the tree.
  await page.evaluate(() => window.treeTest.pickFace('o27_5', 3));
  await page.waitForFunction(() => {
    const row = [...document.querySelectorAll('[aria-label="Model"] > li')].find(li => li.querySelector('[aria-label="Select Part 27-5"]'));
    if (!row?.querySelector('[aria-pressed="true"]')) return false;
    const box = row.getBoundingClientRect(), view = row.closest('[data-tool-panel-body]').getBoundingClientRect();
    return box.top >= view.top - 1 && box.bottom <= view.bottom + 1;
  });
  // The viewport asks for the part the pointer rests on, after the dwell; a pass does not.
  const hover = id => page.evaluate(id => window.treeTest.hoverStore.setModelPartId(id), id);
  await hover('o12_8'); await page.waitForTimeout(40); await hover(''); await page.waitForTimeout(300);
  assert.equal((await topology()).includes('o12_8'), false, 'passing over a part asks for nothing');
  await hover('o12_7'); await page.waitForTimeout(40);
  assert.equal((await topology()).includes('o12_7'), false, 'not before the dwell');
  await page.waitForFunction(() => window.treeTest.events.topology.includes('o12_7'));
  // A press on a part asks at once.
  await hover('o13_1');
  await page.getByTestId('viewport').dispatchEvent('pointerdown');
  assert.equal((await topology()).includes('o13_1'), true, 'a press on a part asks at once');
  await hover('');
  // All is the person's own tree again, unlocked; Parts locks the assemblies open.
  await page.evaluate(() => window.treeTest.setMode('all')); await frames();
  assert.equal(await model.locator('[data-disclosure-locked]').count(), 0);
  await page.evaluate(() => window.treeTest.setMode('parts')); await frames();
  assert.deepEqual(await model.locator('[data-disclosure-locked]').evaluateAll(marks => [...new Set(marks.map(mark => mark.dataset.disclosureLocked))]), ['open']);

  // A small tree (5 groups of 50 parts: 255 rows) under Faces: the parts on screen ask for their
  // topology, once each, as a scroll brings them on screen.
  await page.goto(`http://127.0.0.1:${server.address().port}/?groups=5&parts=50`);
  await model.getByRole('button', { name: 'Select Part 0-0', exact: true }).waitFor();
  await page.evaluate(() => { window.treeTest.events.topology.length = 0; window.treeTest.setMode('faces'); });
  await page.waitForFunction(() => window.treeTest.events.topology.length > 0);
  await frames();
  assert.equal(await model.getByRole('button', { name: /^(Expand|Collapse) Part / }).count(), 0, 'no part has a disclosure to press');
  const onScreen = async () => page.evaluate(() => {
    const scroller = document.querySelector('[aria-label="Model"]').closest('[data-tool-panel-body]'), view = scroller.getBoundingClientRect();
    return [...document.querySelectorAll('[aria-label="Model"] > li[data-tree-part]')].filter(li => { const box = li.getBoundingClientRect(); return box.bottom > view.top && box.top < view.bottom; })
      .map(li => li.dataset.treePart.replace(/^model:/, ''));
  });
  const firstScreen = await onScreen();
  assert.deepEqual((await topology()).sort(), [...firstScreen].sort(), 'the parts on screen, and only those');
  await scrollTo(0.5); await frames(); await frames();
  const secondScreen = await onScreen();
  const requested = await topology();
  assert.equal(new Set(requested).size, requested.length, 'no part is asked for twice');
  assert.deepEqual([...requested].sort(), [...new Set([...firstScreen, ...secondScreen])].sort(), 'the scroll asked for what it brought on screen');
  await page.evaluate(() => window.treeTest.refresh()); await frames();
  assert.equal((await topology()).length, requested.length, 'a re-render asks for nothing');
  // Hover asks for nothing in a small tree: its parts load as their rows show.
  await page.evaluate(() => window.treeTest.hoverStore.setModelPartId('o4_40')); await page.waitForTimeout(400);
  assert.equal((await topology()).includes('o4_40'), false);
  await page.evaluate(() => window.treeTest.hoverStore.setModelPartId(''));
  // A pick in the viewport scrolls the tree to its part's row, however far down: a face under
  // Faces, a part under Parts and under All.
  const inView = label => page.waitForFunction(label => {
    const row = [...document.querySelectorAll('[aria-label="Model"] > li')].find(li => li.querySelector(`[aria-label="Select ${label}"]`));
    if (!row?.querySelector('[aria-pressed="true"]')) return false;
    const box = row.getBoundingClientRect(), view = row.closest('[data-tool-panel-body]').getBoundingClientRect();
    return box.top >= view.top - 1 && box.bottom <= view.bottom + 1;
  }, label);
  await scrollTo(0); await frames();
  await page.evaluate(() => window.treeTest.pickFace('o4_40', 3));
  await inView('Part 4-40');
  await page.evaluate(() => window.treeTest.setMode('parts')); await scrollTo(0); await frames();
  await page.evaluate(() => window.treeTest.select('o4_45'));
  await inView('Part 4-45');
  await page.evaluate(() => window.treeTest.setMode('all')); await scrollTo(0); await frames();
  await page.evaluate(() => window.treeTest.select('o4_30'));
  await inView('Part 4-30');
  assert.deepEqual(errors, []);
});
