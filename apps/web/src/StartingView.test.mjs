import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { build } from 'esbuild';
import { JSDOM } from 'jsdom';
import { createRequire } from 'node:module';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
const temporary = await mkdtemp(join(tmpdir(), 'text-to-cad-web-starting-'));
const output = join(temporary, 'starting.mjs');
await build({
  stdin: { contents: `export {StartingView} from './StartingView.tsx'; export {act,createElement} from 'react'; export {createRoot} from 'react-dom/client'; export {createTabStore} from '@cad/ui/tab-store'; export {sessionTabRecord} from './persistence/tabRecord.ts';`, resolveDir: fileURLToPath(new URL('.', import.meta.url)) },
  bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', outfile: output, loader: { '.css': 'empty', '.svg': 'dataurl' },
  banner: { js: `import {createRequire} from 'node:module'; const require=createRequire(import.meta.url);` },
  plugins: [{ name: 'react-external', setup(plugin) {
    plugin.onResolve({ filter: /^react(?:\/|$)|^react-dom(?:\/|$)/ }, args => ({
      path: args.kind.startsWith('require') ? require.resolve(args.path) : pathToFileURL(require.resolve(args.path)).href,
      external: true,
    }));
  } }],
});
const { StartingView, act, createElement, createRoot, createTabStore, sessionTabRecord } = await import(pathToFileURL(output).href);
after(() => rm(temporary, { recursive: true, force: true }));

const ID = '6f1c2a4e-1b2c-5d3e-8f4a-000000000001';

/** The starting view at `url`, before the server has answered; what it asked the network, kept in `fetched`. `kept`: the tab's record, where it has one. */
async function starting(url, kept = null) {
  const { window } = new JSDOM('<div id="root"></div>', { url, pretendToBeVisual: true });
  const matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {}, addListener() {}, removeListener() {} });
  window.matchMedia = matchMedia;
  window.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} };
  const fetched = [];
  for (const [key, value] of Object.entries({ window, document: window.document, navigator: window.navigator, sessionStorage: window.sessionStorage,
    localStorage: window.localStorage, matchMedia, ResizeObserver: window.ResizeObserver, HTMLElement: window.HTMLElement, Element: window.Element, Node: window.Node,
    getComputedStyle: window.getComputedStyle.bind(window), requestAnimationFrame: callback => setTimeout(callback, 0), cancelAnimationFrame: clearTimeout,
    fetch: async request => { fetched.push(String(request)); return new Response('{}'); }, IS_REACT_ACT_ENVIRONMENT: true })) {
    Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  }
  const root = createRoot(window.document.getElementById('root'));
  const storage = sessionTabRecord(window.sessionStorage);
  if (kept) storage.write(kept);
  await act(() => root.render(createElement(StartingView, { tabStore: createTabStore(storage) })));
  return { document: window.document, fetched, unmount: () => act(() => root.unmount()) };
}

// While the page asks the server what it is, it is the app's own frame as the app's first frame draws it: the navbar,
// inert, and for a document's page the panel's stand-in beside the loading indicator, asking nothing.
test('the starting view is the app\'s frame before the server answers', async () => {
  const page = await starting(`http://cad.local/${ID}`);
  try {
    const view = page.document.querySelector('[data-starting-view]');
    assert.ok(view?.hasAttribute('inert'));
    assert.ok(view.querySelector('header[data-viewer-navbar]'));
    assert.ok(view.querySelector('aside[data-panel-loading]'));
    assert.ok(view.querySelector('[data-loading-step]'));
    // The logo first, the link home it will be, then the panel's toggle, as the app's row has them.
    const row = [...view.querySelectorAll('header[data-viewer-navbar] nav > *')].slice(0, 2);
    assert.deepEqual(row.map(node => node.getAttribute('data-navbar-logo') ?? node.querySelector('[data-navbar-panel="left"]')?.getAttribute('data-navbar-panel')), ['home', 'left']);
    assert.deepEqual(page.fetched, []);
  } finally { await page.unmount(); }
  // The home's address: the home's navbar with its logo first, the link home it will be, then its sidebar's toggle; the
  // sidebar's stand-in (the panel's surface, placeholder rows where its places will be, Settings at its foot), and
  // the indicator on the page's background beside it.
  const home = await starting('http://cad.local/');
  try {
    const lead = [...home.document.querySelectorAll('[data-starting-view] header[data-viewer-navbar] nav > *')];
    assert.deepEqual(lead.map(node => node.querySelector('[data-navbar-panel="left"]')?.getAttribute('aria-expanded') ?? node.getAttribute('data-navbar-logo')), ['home', 'true']);
    assert.deepEqual([lead[0].tagName, lead[0].getAttribute('href'), lead[0].classList.contains('cad-navbar-logo')], ['A', '/', true]);
    const sidebar = home.document.querySelector('[data-starting-home] aside[data-library-sidebar]');
    assert.deepEqual([sidebar.hidden, sidebar.style.width, Boolean(sidebar.querySelector('[data-tree-rows-loading]')), sidebar.querySelectorAll('[data-place]').length,
      Boolean(sidebar.querySelector('[data-app-foot] [data-app-settings]'))], [false, '232px', true, 0, true]);
    assert.ok(home.document.querySelector('[data-starting-home] [data-loading-step]'));
    assert.equal(home.document.querySelector('aside[data-panel-loading]'), null);
    assert.deepEqual(home.fetched, []);
  } finally { await home.unmount(); }
});

// The home's sidebar stands as the tab kept it: shut where the person shut it, at the width they dragged it to.
test('the starting view draws the home\'s sidebar as the tab kept it', async () => {
  const kept = { version: 2, settings: { library: { layout: 'grid', sort: 'activity', panel: { open: false, width: 320 } } }, files: {} };
  const page = await starting('http://cad.local/', kept);
  try {
    const sidebar = page.document.querySelector('[data-starting-home] aside[data-library-sidebar]');
    assert.deepEqual([sidebar.hidden, sidebar.style.width, page.document.querySelector('[data-navbar-panel="left"]').getAttribute('aria-expanded')], [true, '320px', 'false']);
  } finally { await page.unmount(); }
});
