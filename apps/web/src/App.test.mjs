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
  stdin: { contents: `export {default as App} from './App.tsx'; export {createWebCadClient} from './host/cadClient.js'; export {act,createElement} from 'react'; export {createRoot} from 'react-dom/client'; export {snapshot} from '@text-to-cad/ui/cad-viewer'; export {autoReloadOptions} from './host/useViewerAutoReload.js'; export {createTabStore} from '@text-to-cad/ui/tab-store'; export {sessionTabRecord, TAB_RECORD_KEY} from './persistence/tabRecord.ts';`, resolveDir: fileURLToPath(new URL('.', import.meta.url)) },
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
      if (args.path.endsWith('/cad-viewer')) return { contents: `let current; export function CadViewer(props){current=props; return null;} export const snapshot=()=>current; export const createCadFileSource=client=>({id:'local',client}); export const normalizePath=path=>String(path||'').trim().replace(/\\\\/g,'/').replace(/(.)\\/+$/,'$1');`, loader: 'js' };
      if (args.path.endsWith('useViewerAutoReload.js')) return { contents: 'let reloadOptions;export const autoReloadOptions=()=>reloadOptions;export const useViewerAutoReload=(_server,options)=>{reloadOptions=options;return false;};', loader: 'js' };
      if (args.path.endsWith('viewerLinks.js')) return { contents: `const links={version:'0.7.4',release:'r',x:'x',github:'g',discord:'d',issues:'i'}; export const useViewerLinks=()=>links;`, loader: 'js' };
      return { contents: 'export default function ViewerAppearance(){return null}', loader: 'js' };
    });
  } }],
});
const { App, createWebCadClient, act, createElement, createRoot, snapshot, autoReloadOptions, createTabStore, sessionTabRecord, TAB_RECORD_KEY } = await import(pathToFileURL(output).href);
after(() => rm(temporary, { recursive: true, force: true }));

test('the web host keeps the URL, the history, the title and the appearance, and hands the rest to the shared viewer', async () => {
  // A developer's link names the file relative to where this viewer started: the page names it in full.
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
  const guards = [];  // the header no page from another site can send, on each analytics answer and features change
  // The person's features as this Viewer's server keeps them (in their settings: `/__cad/features`).
  let kept = { quickEdit: true };
  const notice = { latest: '0.9.0', version: '0.8.1', text: 'A new version v0.9.0 of text-to-cad is available (currently on v0.8.1)', prompt: 'Update text-to-cad to 0.9.0 from https://github.com/earthtojake/text-to-cad', instructions: 'https://www.texttocad.dev/install' };
  const fetchBefore = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    libraryCalls.push([url, init.body ? JSON.parse(init.body) : null]);
    if (['/__cad/analytics', '/__cad/features'].includes(url) && init.body) guards.push(init.headers?.['x-cadgen-viewer']);
    if (url === '/__cad/features' && init.body) kept = { ...kept, ...JSON.parse(init.body) };
    const reply = url === '/__cad/features' ? kept : url === '/__cad/version' ? { notice }
      : url === '/__cad/recents' ? { recents: [] } : url === '/__cad/pick' ? { path: '/m/picked.step' }
      : url !== '/__cad/analytics' ? { ok: true }
      : init.body ? { ask: false, sharing: false, reason: 'choice', policy: 'p' } : { ask: true, sharing: false, reason: 'unasked', policy: 'p' };
    return new Response(JSON.stringify(reply), { headers: { 'content-type': 'application/json' } });
  };
  // The page's own client over this Viewer's routes, its server's description answered here.
  const client = { ...createWebCadClient({ document: window.document }), serverInfo: async options => { serverCalls.push(options); return { identityToken: 'restarted' }; } };
  const root = createRoot(window.document.getElementById('root'));
  const tabStore = createTabStore(sessionTabRecord(window.sessionStorage));
  const viewer = () => snapshot();
  try {
    const historyAtStart = window.history.length;
    // The update notice comes with the server's description (`main.tsx`): the button draws with the page.
    await act(() => root.render(createElement(App, { client, server: { start: '/m', pick: true, platform: 'darwin' }, tabStore, notice })));
    // The file, by its absolute path, in the URL too, in place of the relative one; the host's file
    // menu and links; the tab's store for everything the viewer keeps.
    assert.equal(viewer().file, '/m/one.step');
    assert.equal(new URL(window.location.href).search, '?file=/m/one.step');
    assert.equal(window.history.length, historyAtStart);
    assert.equal(viewer().host.files.id, 'local');
    assert.equal(viewer().tabStore, tabStore);
    assert.deepEqual(Object.keys(viewer().host.fileActions.perform).sort(), ['copy-path', 'reveal']);
    assert.equal(viewer().host.fileActions.platform, 'darwin', 'Reveal is labeled for the machine the server runs on');
    await viewer().host.fileActions.perform.reveal({ path: '/m/one.step', kind: 'file' });
    assert.deepEqual(libraryCalls.filter(([url]) => url === '/__cad/reveal'), [['/__cad/reveal', { path: '/m/one.step' }]]);
    assert.equal(viewer().host.links.version, '0.7.4');
    assert.equal('navigation' in viewer().host, false, 'navigation is the shared viewer\'s: the host only shows what it is asked to');
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
    await act(() => viewer().onShown('/m/one.step'));
    assert.equal(window.document.title, 'CAD | one.step');
    assert.deepEqual(libraryCalls.filter(([url]) => url === '/__cad/recents'), [['/__cad/recents', { action: 'open', path: '/m/one.step' }]]);
    // CAD's analytics, as the CAD app's: the consent read once, its answer in the app menu. (The
    // model shown is counted, as a code and only with consent, as it joins the library.)
    assert.deepEqual(libraryCalls.filter(([url]) => url.startsWith('/__cad/analytics')), [['/__cad/analytics', null]]);
    // The app menu: Analytics, then Features.
    assert.deepEqual(viewer().appSettings.map(setting => [setting.label, setting.checked]),
      [['Share anonymous usage data', false], ['Quick edit', true]]);
    // The card goes to the viewer (it asks once a model is on screen), and its answer is a card's: the
    // server applies it only to an open question. Answered, it is gone.
    await act(() => viewer().notice.props.onAnswer(false));
    assert.deepEqual(libraryCalls.filter(([url]) => url === '/__cad/analytics').at(-1), ['/__cad/analytics', { share: false, card: true }]);
    assert.equal(viewer().notice, null);
    // A newer release is the update button, as in the CAD app: first in the navbar while this install is
    // behind. A page in a browser cannot reach the agent's chat, so its card only copies the prompt, and
    // nothing it does is kept: the server is only read.
    assert.equal(viewer().update.props.notice.latest, '0.9.0');
    assert.equal(viewer().update.props.send, undefined);
    // Its link to manual installation opens a new tab.
    const opened = [];
    const openBefore = window.open;
    window.open = (...args) => { opened.push(args); return null; };
    viewer().update.props.onLink(notice.instructions);
    window.open = openBefore;
    assert.deepEqual(opened, [[notice.instructions, '_blank', 'noopener,noreferrer']]);
    assert.deepEqual(libraryCalls.filter(([url]) => url === '/__cad/version'), [], 'nothing read: the page started with the notice');
    assert.deepEqual(guards, ['1']);
    // Quick edit, on until the person turns it off: read from this Viewer's server once, and the
    // choice kept there (in their settings, whatever port this is), never in the browser's storage.
    assert.deepEqual(libraryCalls.filter(([url]) => url === '/__cad/features'), [['/__cad/features', null]]);
    assert.deepEqual(viewer().features, { quickEdit: true });
    await act(() => viewer().appSettings.find(setting => setting.id === 'quickEdit').onCheckedChange(false));
    assert.deepEqual(libraryCalls.filter(([url]) => url === '/__cad/features').at(-1), ['/__cad/features', { quickEdit: false }]);
    assert.deepEqual(guards, ['1', '1']);
    assert.deepEqual(viewer().features, { quickEdit: false });
    assert.equal(viewer().appSettings.find(setting => setting.id === 'quickEdit').checked, false);
    assert.equal(window.localStorage.length, 0);
    // Coming back to the page reads it again: another view may have changed it meanwhile.
    kept = { quickEdit: true };
    await act(() => { window.dispatchEvent(new window.Event('focus')); });
    assert.deepEqual(viewer().features, { quickEdit: true });

    // Showing another file is a navigation: pushed, and undone by Back.
    const historyLength = window.history.length;
    await act(() => viewer().onShow('/m/folder\\two.step'));
    assert.equal(viewer().file, '/m/folder/two.step');
    assert.equal(new URL(window.location.href).searchParams.get('file'), '/m/folder/two.step');
    assert.equal(window.history.length, historyLength + 1);
    await act(() => viewer().onShow('/m/folder/two.step'));
    assert.equal(window.history.length, historyLength + 1, 'the file on screen is no navigation at all');
    await act(() => { window.history.replaceState({}, '', '?file=/m/one.step'); window.dispatchEvent(new window.PopStateEvent('popstate')); });
    assert.equal(viewer().file, '/m/one.step');
    // A URL that names no file shows the home: the library every CAD view shares, and Open.
    await act(() => { window.history.replaceState({}, '', '/'); window.dispatchEvent(new window.PopStateEvent('popstate')); });
    assert.equal(viewer().file, '');
    await act(() => viewer().onShown(null));
    assert.equal(window.document.title, 'CAD');
    assert.deepEqual(await viewer().library.list(), []);
    assert.equal(libraryCalls.at(-1)[0], '/__cad/recents');
    assert.equal(await viewer().library.thumbnail('abc'), '/__cad/thumbnail?name=abc');
    // A model opened from the home, and one picked with Open, are shown here, each a new step.
    await act(() => viewer().library.open({ path: '/m/folder/two.step' }));
    assert.equal(viewer().file, '/m/folder/two.step');
    await act(() => viewer().library.pick());
    assert.deepEqual(libraryCalls.at(-1), ['/__cad/pick', null]);
    assert.equal(viewer().file, '/m/picked.step');
    assert.equal(new URL(window.location.href).searchParams.get('file'), '/m/picked.step');
    // The home's home button (the logo) leads to the bare URL.
    await act(() => viewer().onShow(''));
    assert.equal(new URL(window.location.href).search, '');
  } finally {
    globalThis.fetch = fetchBefore;
    await act(() => root.unmount());
    assert.equal(appearanceListeners.size, 0);
    dom.window.close();
  }
});
