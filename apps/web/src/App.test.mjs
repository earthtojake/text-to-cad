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
const temporary = await mkdtemp(join(tmpdir(), 'text-to-cad-web-app-'));
const output = join(temporary, 'app.mjs');
await build({
  stdin: { contents: `export {default as App} from './App.tsx'; export {act,createElement} from 'react'; export {createRoot} from 'react-dom/client'; export {snapshot} from '@text-to-cad/ui/cad-viewer'; export {autoReloadOptions} from './host/useViewerAutoReload.js'; export {createTabStore} from '@text-to-cad/ui/tab-store'; export {sessionTabRecord, TAB_RECORD_KEY} from './persistence/tabRecord.ts';`, resolveDir: fileURLToPath(new URL('.', import.meta.url)) },
  bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', outfile: output, loader: { '.css': 'empty', '.svg': 'dataurl' },
  banner: { js: `import {createRequire} from 'node:module'; const require=createRequire(import.meta.url);` },
  plugins: [{ name: 'host-boundaries', setup(plugin) {
    plugin.onResolve({ filter: /^react(?:\/|$)|^react-dom(?:\/|$)/ }, args => ({
      path: args.kind.startsWith('require') ? require.resolve(args.path) : pathToFileURL(require.resolve(args.path)).href,
      external: true,
    }));
    // The shared CAD viewer, reduced to what this host hands it: what it draws is its own suite's.
    plugin.onResolve({ filter: /^@text-to-cad\/ui\/cad-viewer$|ViewerAppearance\.jsx$|useViewerAutoReload\.js$|host\/viewerLinks\.js$/ }, args => ({ path: args.path, namespace: 'host-test' }));
    // The tab store the host really uses; nothing else of the shared UI renders here.
    plugin.onResolve({ filter: /^@text-to-cad\/ui\/tab-store$/ }, () => ({ path: fileURLToPath(new URL('../../../packages/ui/src/tab-store/index.ts', import.meta.url)) }));
    plugin.onLoad({ filter: /.*/, namespace: 'host-test' }, args => {
      if (args.path.endsWith('/cad-viewer')) return { contents: `let current; export function CadViewer(props){current=props; return null;} export const snapshot=()=>current; export const createCatalogFileSource=(client,{id,rootName})=>({id,rootName});`, loader: 'js' };
      if (args.path.endsWith('useViewerAutoReload.js')) return { contents: 'let reloadOptions;export const autoReloadOptions=()=>reloadOptions;export const useViewerAutoReload=(_server,options)=>{reloadOptions=options;return false;};', loader: 'js' };
      if (args.path.endsWith('viewerLinks.js')) return { contents: `const links={version:'0.7.4',release:'r',x:'x',github:'g',discord:'d',issues:'i',install:{command:'c',prompt:'p'}}; export const useViewerLinks=()=>links;`, loader: 'js' };
      return { contents: 'export default function ViewerAppearance(){return null}', loader: 'js' };
    });
  } }],
});
const { App, act, createElement, createRoot, snapshot, autoReloadOptions, createTabStore, sessionTabRecord, TAB_RECORD_KEY } = await import(pathToFileURL(output).href);
after(() => rm(temporary, { recursive: true, force: true }));

test('the web host keeps the URL, the history, the title and the appearance, and hands the rest to the shared viewer', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://cad.local/?file=one.step' });
  const { window } = dom;
  let systemDark = false;
  const appearanceListeners = new Set();
  const matchMedia = () => ({ get matches() { return systemDark; }, addEventListener(_name, listener) { appearanceListeners.add(listener); }, removeEventListener(_name, listener) { appearanceListeners.delete(listener); } });
  for (const [key, value] of Object.entries({ window, document: window.document, navigator: window.navigator, localStorage: window.localStorage, sessionStorage: window.sessionStorage, matchMedia, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  window.matchMedia = matchMedia;
  const serverCalls = [];
  // The library every CAD view shares, written over this Viewer's routes.
  const libraryCalls = [];
  const fetchBefore = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    libraryCalls.push([url, init.body ? JSON.parse(init.body) : null]);
    return new Response(JSON.stringify({ ok: true }), { headers: { 'content-type': 'application/json' } });
  };
  const client = { serverInfo: async options => { serverCalls.push(options); return { identityToken: 'restarted' }; } };
  const root = createRoot(window.document.getElementById('root'));
  const tabStore = createTabStore(sessionTabRecord(window.sessionStorage));
  const viewer = () => snapshot();
  try {
    await act(() => root.render(createElement(App, { client, server: { rootId: 'a', rootPath: '/models', backend: 'local-fs', serverFeatures: ['reveal-path'] }, tabStore })));
    // The served folder's catalog, the host's file menu and its links; the tab's store for everything the viewer keeps.
    assert.equal(viewer().host.files.id, 'a');
    assert.equal(viewer().tabStore, tabStore);
    assert.equal(viewer().rootPath, '/models');
    assert.deepEqual(Object.keys(viewer().host.fileActions.perform).sort(), ['copy-path', 'copy-relative-path', 'reveal']);
    assert.equal(viewer().host.links.version, '0.7.4');
    assert.equal('navigation' in viewer().host, false, 'navigation is the shared viewer\'s: the host only shows what it is asked to');
    assert.equal(viewer().file, 'one.step');
    assert.deepEqual(await autoReloadOptions().fetchServerInfo(), { ok: true, identityToken: 'restarted' });
    assert.deepEqual(serverCalls[0], { fresh: true });

    // The appearance is the tab's, resolved against the OS.
    assert.equal(viewer().displayActions.props.colorSchemePreference, 'system');
    assert.equal(viewer().displayActions.props.resolvedColorSchemeMode, 'light');
    await act(() => { systemDark = true; for (const listener of appearanceListeners) listener(); });
    assert.equal(viewer().displayActions.props.resolvedColorSchemeMode, 'dark');
    assert.equal(viewer().host.environment.colorScheme, 'dark');
    assert.equal(window.document.documentElement.classList.contains('dark'), true);
    await act(() => viewer().displayActions.props.onColorSchemePreferenceChange('light'));
    assert.equal(viewer().host.environment.colorScheme, 'light');
    assert.equal(window.document.documentElement.classList.contains('dark'), false);
    // In the tab's record, under no key of its own and in no cookie.
    assert.equal(JSON.parse(window.sessionStorage.getItem(TAB_RECORD_KEY)).settings.appearance, 'light');
    assert.equal(window.localStorage.length, 0);
    assert.equal(window.document.cookie, '');

    // Once the catalog has the file, the page is named after it and it joins the library.
    await act(() => viewer().onShown('one.step'));
    assert.equal(window.document.title, 'CAD | one.step');
    assert.deepEqual(libraryCalls.filter(([url]) => url === '/__cad/recents'), [['/__cad/recents', { action: 'open', file: 'one.step' }]]);
    // CAD's analytics, as the CAD app's: the consent read once, its answer in Settings, and the model
    // shown reported to this Viewer's server (which keeps it as a code, and sends it only with consent).
    assert.deepEqual(libraryCalls.filter(([url]) => url.startsWith('/__cad/analytics')),
      [['/__cad/analytics', null], ['/__cad/analytics/activity', { file: 'one.step' }]]);
    assert.equal(viewer().appSettings[0].section, 'Analytics');

    // Showing another file is a navigation: pushed, and undone by Back.
    const historyLength = window.history.length;
    await act(() => viewer().onShow('folder\\two.step'));
    assert.equal(viewer().file, 'folder/two.step');
    assert.equal(new URL(window.location.href).searchParams.get('file'), 'folder/two.step');
    assert.equal(window.history.length, historyLength + 1);
    await act(() => viewer().onShow('folder/two.step'));
    assert.equal(window.history.length, historyLength + 1, 'the file on screen is no navigation at all');
    await act(() => { window.history.replaceState({}, '', '?file=one.step'); window.dispatchEvent(new window.PopStateEvent('popstate')); });
    assert.equal(viewer().file, 'one.step');
    // A URL that names no file shows none, and the page is plain CAD.
    await act(() => { window.history.replaceState({}, '', '/'); window.dispatchEvent(new window.PopStateEvent('popstate')); });
    assert.equal(viewer().file, '');
    await act(() => viewer().onShown(null));
    assert.equal(window.document.title, 'CAD');
    // No home: the library is the sidebar's to show, and this Viewer only writes to it.
    assert.equal(viewer().library, undefined);
    // A file the URL did not name (a build's default) is written there once the catalog has it.
    await act(() => viewer().onShown('folder/two.step'));
    assert.equal(new URL(window.location.href).searchParams.get('file'), 'folder/two.step');

    // Another root, the same tab: a new catalog, the same store.
    await act(() => root.render(createElement(App, { client, server: { rootId: 'b', rootPath: '/other' }, tabStore })));
    assert.equal(viewer().host.files.id, 'b');
    assert.equal(viewer().tabStore, tabStore);
  } finally {
    globalThis.fetch = fetchBefore;
    await act(() => root.unmount());
    assert.equal(appearanceListeners.size, 0);
    dom.window.close();
  }
});
