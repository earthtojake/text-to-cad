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
const temporary = await mkdtemp(join(tmpdir(), 'hardcore-web-app-'));
const output = join(temporary, 'app.mjs');
await build({
  stdin: { contents: `export {default as App} from './App.tsx'; export {act,createElement} from 'react'; export {createRoot} from 'react-dom/client'; export {snapshot} from '@hardcore/ui/file-viewer'; export {topBarSnapshot} from './client/components/workbench/ViewerTopBar.jsx'; export {autoReloadOptions} from './host/useViewerAutoReload.js';`, resolveDir: fileURLToPath(new URL('.', import.meta.url)) },
  bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', outfile: output,
  banner: { js: `import {createRequire} from 'node:module'; const require=createRequire(import.meta.url);` },
  plugins: [{ name: 'host-boundaries', setup(plugin) {
    plugin.onResolve({ filter: /^react(?:\/|$)|^react-dom(?:\/|$)/ }, args => ({
      path: args.kind.startsWith('require') ? require.resolve(args.path) : pathToFileURL(require.resolve(args.path)).href,
      external: true,
    }));
    plugin.onResolve({ filter: /^@hardcore\/ui\/file-viewer$|^@hardcore\/ui\/renderers\/(step|dxf|glb|mesh|robot|workspace)$|^@hardcore\/ui\/file-viewer\/(presentation|empty)$|ViewerTopBar\.jsx$|useViewerAutoReload\.js$/ }, args => ({ path: args.path, namespace: 'host-test' }));
    plugin.onLoad({ filter: /.*/, namespace: 'host-test' }, args => {
      if (args.path.endsWith('/file-viewer')) return { contents: `let current; export function FileViewer(props){current=props; return null;} export const snapshot=()=>current;`, loader: 'js' };
      if (args.path.endsWith('/step')) return { contents: `export const createStepRenderer=()=>({id:'step'});`, loader: 'js' };
      // The preferences the host really uses; everything else the workspace module pulls in is a renderer's.
      if (args.path.endsWith('/workspace')) return { contents: `export {createCadPreferences,CAD_LEGACY_PREFERENCE_KEYS} from ${JSON.stringify(fileURLToPath(new URL('../../../packages/ui/src/renderers/workspace/preferences.ts', import.meta.url)))};`, loader: 'js', resolveDir: fileURLToPath(new URL('.', import.meta.url)) };
      if (args.path.endsWith('/dxf')) return { contents: `export const createDxfRenderer=()=>({id:'dxf'});`, loader: 'js' };
      if (args.path.endsWith('/glb')) return { contents: `export const createGlbRenderer=()=>({id:'glb'});`, loader: 'js' };
      if (args.path.endsWith('/mesh')) return { contents: `export const createMeshRenderer=()=>({id:'mesh'});`, loader: 'js' };
      if (args.path.endsWith('/robot')) return { contents: `export const createRobotRenderer=()=>({id:'robot'});`, loader: 'js' };
      if (args.path.endsWith('useViewerAutoReload.js')) return { contents: 'let reloadOptions;export const autoReloadOptions=()=>reloadOptions;export const useViewerAutoReload=(_server,options)=>{reloadOptions=options;return false;};', loader: 'js' };
      if (args.path.endsWith('/presentation')) return { contents: 'export const MissingFileAlert=()=>null;export const ViewerLoadingOverlay=()=>null;export const StatusToast=()=>null;', loader: 'js' };
      if (args.path.endsWith('/empty')) return { contents: 'export const EmptyCadBackdrop=({children})=>children;', loader: 'js' };
      return { contents: 'let current; export default function ViewerTopBar(props){current=props; return null} export const topBarSnapshot=()=>current;', loader: 'js' };
    });
  } }],
});
const { App, act, createElement, createRoot, snapshot, topBarSnapshot, autoReloadOptions } = await import(pathToFileURL(output).href);
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
  try {
    await act(() => root.render(createElement(App, { client, server: { rootId: 'a' } })));
    // One viewer renderer per file family, registered together.
    assert.deepEqual(snapshot().renderers.map(renderer => renderer.id), ['step', 'dxf', 'glb', 'mesh', 'robot']);
    assert.equal(topBarSnapshot().colorSchemePreference, 'system');
    assert.equal(topBarSnapshot().resolvedColorSchemeMode, 'light');
    await act(() => { systemDark = true; for (const listener of appearanceListeners) listener(); });
    assert.equal(topBarSnapshot().colorSchemePreference, 'system');
    assert.equal(topBarSnapshot().resolvedColorSchemeMode, 'dark');
    await act(() => topBarSnapshot().onColorSchemePreferenceChange('light'));
    assert.equal(topBarSnapshot().colorSchemePreference, 'light');
    assert.equal(topBarSnapshot().resolvedColorSchemeMode, 'light');
    await act(() => topBarSnapshot().onColorSchemePreferenceChange('system'));
    assert.equal(topBarSnapshot().resolvedColorSchemeMode, 'dark');
    assert.equal(snapshot().file, 'one.step');
    assert.deepEqual(await autoReloadOptions().fetchServerInfo(), { ok: true, identityToken: 'restarted' });
    assert.deepEqual(serverCalls[0], { fresh: true });
    assert.equal(snapshot().navigationPath, null);
    await act(() => {
      catalog = { ...catalog, entries: [{ file: 'one.step' }, { file: 'folder/two.step' }], hydrated: true, refreshing: false, revision: 1 };
      for (const listener of listeners) listener();
    });
    assert.equal(snapshot().navigationPath, 'one.step');
    assert.equal(snapshot().state.panel, 'tree');
    assert.equal(snapshot().narrowCrumbs, false);
    assert.equal(window.document.title, 'text-to-cad | one.step');
    const historyLength = window.history.length;
    await act(() => snapshot().host.navigation.openFile('missing.step'));
    assert.equal(window.history.length, historyLength);
    assert.equal(snapshot().file, 'one.step');
    await act(() => snapshot().host.navigation.openFile('folder\\two.step'));
    assert.equal(snapshot().file, 'folder/two.step');
    assert.equal(snapshot().state.panel, '');
    assert.equal(window.history.length, historyLength + 1);
    assert.equal(new URL(window.location.href).searchParams.get('file'), 'folder/two.step');
    await act(() => { window.history.replaceState({}, '', '?file=one.step'); window.dispatchEvent(new window.PopStateEvent('popstate')); });
    assert.equal(snapshot().file, 'one.step');
    await act(() => { window.history.replaceState({}, '', '?file=missing.step'); window.dispatchEvent(new window.PopStateEvent('popstate')); });
    assert.equal(snapshot().file, 'missing.step');
    assert.equal(snapshot().navigationPath, null);
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
    await act(() => root.render(createElement(App, { client, server: { rootId: 'b' } })));
    assert.equal(snapshot().host.files.id, 'b');
    assert.equal(snapshot().state.panel, 'tree');
    assert.equal(JSON.parse(window.sessionStorage.getItem('hardcore:file-viewer:v1:a')).panel, '');
    assert.equal(JSON.parse(window.sessionStorage.getItem('hardcore:file-viewer:v1:b')).panel, 'tree');
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
