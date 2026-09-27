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
  stdin: { contents: `export {default as App} from './App.tsx'; export {act,createElement} from 'react'; export {createRoot} from 'react-dom/client'; export {snapshot} from '@text-to-cad/ui/file-viewer'; export {autoReloadOptions} from './host/useViewerAutoReload.js'; export {createTabStore} from '@text-to-cad/ui/tab-store'; export {sessionTabRecord, TAB_RECORD_KEY} from './persistence/tabRecord.ts';`, resolveDir: fileURLToPath(new URL('.', import.meta.url)) },
  bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', outfile: output, loader: { '.css': 'empty' },
  banner: { js: `import {createRequire} from 'node:module'; const require=createRequire(import.meta.url);` },
  plugins: [{ name: 'host-boundaries', setup(plugin) {
    plugin.onResolve({ filter: /^react(?:\/|$)|^react-dom(?:\/|$)/ }, args => ({
      path: args.kind.startsWith('require') ? require.resolve(args.path) : pathToFileURL(require.resolve(args.path)).href,
      external: true,
    }));
    plugin.onResolve({ filter: /^@text-to-cad\/ui\/file-viewer$|^@text-to-cad\/ui\/renderers\/(step|dxf|glb|mesh|robot)$|^@text-to-cad\/ui\/file-viewer\/(presentation|empty)$|(?:ViewerAppearance|ViewerBrand|ViewerLinks)\.jsx$|useViewerAutoReload\.js$/ }, args => ({ path: args.path, namespace: 'host-test' }));
    // The tab store the host really uses; nothing else of the shared UI renders here.
    plugin.onResolve({ filter: /^@text-to-cad\/ui\/tab-store$/ }, () => ({ path: fileURLToPath(new URL('../../../packages/ui/src/tab-store/index.ts', import.meta.url)) }));
    plugin.onLoad({ filter: /.*/, namespace: 'host-test' }, args => {
      if (args.path.endsWith('/file-viewer')) return { contents: `let current; export function FileViewer(props){current=props; return null;} export const snapshot=()=>current;`, loader: 'js' };
      if (args.path.endsWith('/step')) return { contents: `export const createStepRenderer=({preferences})=>({id:'step', preferences});`, loader: 'js' };
      if (args.path.endsWith('/dxf')) return { contents: `export const createDxfRenderer=()=>({id:'dxf'});`, loader: 'js' };
      if (args.path.endsWith('/glb')) return { contents: `export const createGlbRenderer=()=>({id:'glb'});`, loader: 'js' };
      if (args.path.endsWith('/mesh')) return { contents: `export const createMeshRenderer=()=>({id:'mesh'});`, loader: 'js' };
      if (args.path.endsWith('/robot')) return { contents: `export const createRobotRenderer=()=>({id:'robot'});`, loader: 'js' };
      if (args.path.endsWith('useViewerAutoReload.js')) return { contents: 'let reloadOptions;export const autoReloadOptions=()=>reloadOptions;export const useViewerAutoReload=(_server,options)=>{reloadOptions=options;return false;};', loader: 'js' };
      if (args.path.endsWith('/presentation')) return { contents: 'export const MissingFileAlert=()=>null;export const ViewerLoadingOverlay=()=>null;', loader: 'js' };
      if (args.path.endsWith('/empty')) return { contents: 'export const EmptyCadBackdrop=({children})=>children;', loader: 'js' };
      return { contents: 'let current; export default function ViewerAppearance(props){current=props; return null} export const topBarSnapshot=()=>current;', loader: 'js' };
    });
  } }],
});
const { App, act, createElement, createRoot, snapshot, autoReloadOptions, createTabStore, sessionTabRecord, TAB_RECORD_KEY } = await import(pathToFileURL(output).href);
after(() => rm(temporary, { recursive: true, force: true }));

test('web host preserves compact navigation, history, root state and focus refresh lifecycle', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'http://cad.local/?file=one.step' });
  const { window } = dom;
  let systemDark = false;
  const appearanceListeners = new Set();
  const matchMedia = () => ({ get matches() { return systemDark; }, addEventListener(_name, listener) { appearanceListeners.add(listener); }, removeEventListener(_name, listener) { appearanceListeners.delete(listener); } });
  for (const [key, value] of Object.entries({ window, document: window.document, navigator: window.navigator, localStorage: window.localStorage, sessionStorage: window.sessionStorage, matchMedia, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  window.matchMedia = matchMedia;
  window.innerWidth = 480;
  const calls = [];
  const serverCalls = [];
  const listeners = new Set();
  let catalog = { entries: [], hydrated: false, refreshing: true, error: '', revision: 0, rootId: 'a' };
  const client = { serverInfo: async options => { serverCalls.push(options); return { identityToken: "restarted" }; }, getSnapshot: () => catalog, subscribe: listener => { listeners.add(listener); return () => listeners.delete(listener); }, refresh: async options => { calls.push(options); return { entries: catalog.entries }; } };
  const root = createRoot(window.document.getElementById('root'));
  const tabStore = createTabStore(sessionTabRecord(window.sessionStorage));
  try {
    await act(() => root.render(createElement(App, { client, server: { rootId: 'a' }, tabStore })));
    // One viewer renderer per file family, registered together, every one reading the tab's settings.
    assert.deepEqual(snapshot().renderers.map(renderer => renderer.id), ['step', 'dxf', 'glb', 'mesh', 'robot']);
    assert.equal(snapshot().renderers[0].preferences, tabStore.settings);
    assert.equal(snapshot().displayActions.props.colorSchemePreference, 'system');
    assert.equal(snapshot().displayActions.props.resolvedColorSchemeMode, 'light');
    await act(() => { systemDark = true; for (const listener of appearanceListeners) listener(); });
    assert.equal(snapshot().displayActions.props.colorSchemePreference, 'system');
    assert.equal(snapshot().displayActions.props.resolvedColorSchemeMode, 'dark');
    await act(() => snapshot().displayActions.props.onColorSchemePreferenceChange('light'));
    assert.equal(snapshot().displayActions.props.colorSchemePreference, 'light');
    assert.equal(snapshot().displayActions.props.resolvedColorSchemeMode, 'light');
    assert.equal(snapshot().host.environment.colorScheme, 'light');
    assert.equal(window.document.documentElement.classList.contains('dark'), false);
    // The appearance is the tab's: in its record, under no key of its own and in no cookie.
    assert.equal(JSON.parse(window.sessionStorage.getItem(TAB_RECORD_KEY)).settings.appearance, 'light');
    assert.equal(window.localStorage.length, 0);
    assert.equal(window.document.cookie, '');
    await act(() => snapshot().displayActions.props.onColorSchemePreferenceChange('system'));
    assert.equal(snapshot().displayActions.props.resolvedColorSchemeMode, 'dark');
    assert.equal(window.document.documentElement.classList.contains('dark'), true);
    assert.equal(snapshot().file, 'one.step');
    assert.deepEqual(await autoReloadOptions().fetchServerInfo(), { ok: true, identityToken: 'restarted' });
    assert.deepEqual(serverCalls[0], { fresh: true });
    assert.equal(snapshot().navigationPath, null);
    assert.equal(snapshot().leading.props.title, 'text-to-cad', 'while the file is resolving there are no crumbs, so the app names itself');
    await act(() => {
      catalog = { ...catalog, entries: [{ file: 'one.step' }, { file: 'folder/two.step' }], hydrated: true, refreshing: false, revision: 1 };
      for (const listener of listeners) listener();
    });
    assert.equal(snapshot().navigationPath, 'one.step');
    assert.equal(snapshot().leading.props.title, '', 'once the crumbs name the file the title goes');
    // A page load is a file opened directly, so it opens on that file's own default panel
    // (`null`) — a narrow window included — and never on one a previous page left open.
    assert.equal(snapshot().state.panel, null);
    assert.equal('narrowCrumbs' in snapshot(), false);
    assert.equal('fullscreen' in snapshot(), false, 'fullscreen is each viewer\'s own, never the host\'s');
    assert.equal('lifecycle' in snapshot().host, false);
    assert.equal(window.document.title, 'text-to-cad | one.step');
    const historyLength = window.history.length;
    await act(() => snapshot().host.navigation.openFile('missing.step'));
    assert.equal(window.history.length, historyLength);
    assert.equal(snapshot().file, 'one.step');
    await act(() => snapshot().host.navigation.openFile('folder\\two.step'));
    assert.equal(snapshot().file, 'folder/two.step');
    // The host applies the panel at every width — FileViewer owns the mobile layout itself
    // (floating sheets it closes on an open) — so a plain open lands on the file's default.
    assert.equal(snapshot().state.panel, null);
    assert.equal(window.history.length, historyLength + 1);
    assert.equal(new URL(window.location.href).searchParams.get('file'), 'folder/two.step');
    await act(() => snapshot().host.navigation.openFile('one.step', { target: 'new', panel: 'tree' }));
    assert.equal(snapshot().state.panel, 'tree', 'and one picked in the tree asks for the tree');
    assert.equal(window.history.length, historyLength + 2);
    // The file already shown keeps whatever it has open unless a panel is asked for.
    window.innerWidth = 1280;
    await act(() => snapshot().host.navigation.openFile('folder\\two.step', { target: 'new', panel: 'tree' }));
    assert.equal(snapshot().file, 'folder/two.step');
    assert.equal(snapshot().state.panel, 'tree');
    assert.equal(window.history.length, historyLength + 3);
    await act(() => snapshot().host.navigation.openFile('folder\\two.step', { target: 'current' }));
    assert.equal(snapshot().state.panel, 'tree', 'the shown file opened with no panel keeps the one it has');
    assert.equal(window.history.length, historyLength + 3, 'and is no navigation at all');
    await act(() => snapshot().host.navigation.openFile('folder\\two.step', { target: 'new', panel: '' }));
    assert.equal(snapshot().state.panel, '', 'the shown file opened with a panel takes it');
    assert.equal(window.history.length, historyLength + 3);
    await act(() => snapshot().host.navigation.openFile('one.step', { target: 'current' }));
    assert.equal(snapshot().file, 'one.step');
    assert.equal(snapshot().state.panel, null, 'another file opened with no panel opens on its own default');
    window.innerWidth = 480;
    await act(() => { window.history.replaceState({}, '', '?file=one.step'); window.dispatchEvent(new window.PopStateEvent('popstate')); });
    assert.equal(snapshot().file, 'one.step');
    await act(() => { window.history.replaceState({}, '', '?file=folder/missing.step'); window.dispatchEvent(new window.PopStateEvent('popstate')); });
    assert.equal(snapshot().file, 'folder/missing.step');
    assert.equal(snapshot().navigationPath, 'folder/missing.step', 'a missing file, nested or not, keeps its crumbs once the catalog has answered');
    assert.equal(snapshot().leading.props.title, '', 'a file, even a missing one, is named by its crumbs');
    // No file at all: the app names itself beside its icon, where the crumbs would be.
    await act(() => { window.history.replaceState({}, '', '/'); window.dispatchEvent(new window.PopStateEvent('popstate')); });
    assert.ok(!snapshot().file);
    assert.equal(snapshot().leading.props.title, 'text-to-cad');
    await act(() => { window.history.replaceState({}, '', '?file=one.step'); window.dispatchEvent(new window.PopStateEvent('popstate')); });
    await act(() => window.dispatchEvent(new window.Event('focus')));
    assert.equal(calls.length, 1);
    assert.equal(calls[0].markRefreshing, false);
    Object.defineProperty(window.document, 'visibilityState', { configurable: true, value: 'hidden' });
    await act(() => window.document.dispatchEvent(new window.Event('visibilitychange')));
    assert.equal(calls.length, 1);
    Object.defineProperty(window.document, 'visibilityState', { configurable: true, value: 'visible' });
    await act(() => window.document.dispatchEvent(new window.Event('visibilitychange')));
    assert.equal(calls.length, 2);
    // What the viewer hands back lands in the tab record: the column's width and this root's open
    // folders in the tab's settings, a file's view under the root, the file and the renderer.
    await act(() => snapshot().onStateChange({ ...snapshot().state, panelWidth: 300, expandedDirectories: ['folder'], renderers: { ...snapshot().state.renderers, [JSON.stringify(['one.step', 'step'])]: { version: 2, camera: null, display: null, renderer: {} } } }));
    assert.deepEqual([snapshot().state.panelWidth, snapshot().state.expandedDirectories], [300, ['folder']]);
    const record = JSON.parse(window.sessionStorage.getItem(TAB_RECORD_KEY));
    assert.deepEqual(record.settings.fileTree, { width: 300, expanded: { a: ['folder'] } });
    assert.deepEqual(Object.keys(record.files), [JSON.stringify(['a', 'one.step', 'step'])]);
    assert.equal('panel' in record, false, 'the open panel is never stored');
    await act(() => root.render(createElement(App, { client, server: { rootId: 'b' }, tabStore })));
    assert.equal(snapshot().host.files.id, 'b');
    // Another root, the same tab: the column's width is the tab's, the folders and the views the root's.
    assert.equal(snapshot().state.panel, null);
    assert.deepEqual([snapshot().state.panelWidth, snapshot().state.expandedDirectories, snapshot().state.renderers], [300, [], {}]);
    assert.equal(calls[0].signal.aborted, true);
  } finally {
    await act(() => root.unmount());
    window.dispatchEvent(new window.Event('focus'));
    assert.equal(calls.length, 2);
    assert.equal(listeners.size, 0);
    assert.equal(appearanceListeners.size, 0);
    dom.window.close();
  }
});
