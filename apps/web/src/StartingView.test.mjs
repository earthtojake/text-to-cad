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

/** The starting view at `url`, before the server has answered; what it asked the network, kept in `fetched`. */
async function starting(url) {
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
  await act(() => root.render(createElement(StartingView, { tabStore: createTabStore(sessionTabRecord(window.sessionStorage)) })));
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
    assert.deepEqual(page.fetched, []);
  } finally { await page.unmount(); }
  // The home's address: the home's navbar with its logo, no panel, and the indicator on the page's background.
  const home = await starting('http://cad.local/');
  try {
    assert.ok(home.document.querySelector('[data-starting-view] header[data-viewer-navbar] .cad-navbar-logo'));
    assert.ok(home.document.querySelector('[data-starting-home] [data-loading-step]'));
    assert.equal(home.document.querySelector('aside[data-panel-loading]'), null);
    assert.deepEqual(home.fetched, []);
  } finally { await home.unmount(); }
});
