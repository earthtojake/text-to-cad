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
  stdin: { contents: `export {default as App} from './App.tsx'; export {EngineStopped} from './EngineStopped.tsx'; export {createWebCadClient} from './host/cadClient.js'; export {act,createElement} from 'react'; export {createRoot} from 'react-dom/client'; export {snapshot} from '@text-to-cad/ui/cad-viewer'; export {autoReloadOptions} from './host/useViewerAutoReload.js'; export {createTabStore} from '@text-to-cad/ui/tab-store'; export {sessionTabRecord, TAB_RECORD_KEY} from './persistence/tabRecord.ts';`, resolveDir: fileURLToPath(new URL('.', import.meta.url)) },
  bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', outfile: output, loader: { '.css': 'empty', '.svg': 'dataurl' },
  banner: { js: `import {createRequire} from 'node:module'; const require=createRequire(import.meta.url);` },
  plugins: [{ name: 'host-boundaries', setup(plugin) {
    plugin.onResolve({ filter: /^react(?:\/|$)|^react-dom(?:\/|$)/ }, args => ({
      path: args.kind.startsWith('require') ? require.resolve(args.path) : pathToFileURL(require.resolve(args.path)).href,
      external: true,
    }));
    // The shared CAD viewer, reduced to what this host hands it: what it draws is its own suite's.
    plugin.onResolve({ filter: /^@text-to-cad\/ui\/cad-viewer$|useViewerAutoReload\.js$|host\/viewerLinks\.js$/ }, args => ({ path: args.path, namespace: 'host-test' }));
    // The tab store the host really uses; nothing else of the shared UI renders here.
    plugin.onResolve({ filter: /^@text-to-cad\/ui\/tab-store$/ }, () => ({ path: fileURLToPath(new URL('../../../packages/ui/src/tab-store/index.ts', import.meta.url)) }));
    plugin.onLoad({ filter: /.*/, namespace: 'host-test' }, args => {
      if (args.path.endsWith('/cad-viewer')) return { contents: `let current; export function CadViewer(props){current=props; return null;} export const snapshot=()=>current; export const createCadFileSource=client=>({id:'local',client}); export const normalizePath=path=>String(path||'').trim().replace(/\\\\/g,'/').replace(/(.)\\/+$/,'$1');`, loader: 'js' };
      if (args.path.endsWith('useViewerAutoReload.js')) return { contents: 'let reloadOptions;export const autoReloadOptions=()=>reloadOptions;export const useViewerAutoReload=(_server,options)=>{reloadOptions=options;return false;};', loader: 'js' };
      return { contents: `const links={version:'0.7.4',release:'r',x:'x',github:'g',discord:'d',issues:'i'}; export const useViewerLinks=()=>links;`, loader: 'js' };
    });
  } }],
});
const { App, EngineStopped, createWebCadClient, act, createElement, createRoot, snapshot, autoReloadOptions, createTabStore, sessionTabRecord, TAB_RECORD_KEY } = await import(pathToFileURL(output).href);
after(() => rm(temporary, { recursive: true, force: true }));

// Each file's document id, as the server derives it from the file's canonical path.
const IDS = { '/m/one.step': '6f1c2a4e-1b2c-5d3e-8f4a-000000000001', '/m/folder/two.step': '6f1c2a4e-1b2c-5d3e-8f4a-000000000002',
  '/m/picked.step': '6f1c2a4e-1b2c-5d3e-8f4a-000000000003' };
const ONE = IDS['/m/one.step'], TWO = IDS['/m/folder/two.step'], PICKED = IDS['/m/picked.step'];
/** Whether `url` (with its `init`) is the catalog's read of one document: by its path, or its id. */
const isCatalog = (url, init = {}) => (init.method ?? 'GET') === 'GET' && (url.startsWith('/api/v1/documents?path=') || /^\/api\/v1\/documents\/[0-9a-f-]{36}$/.test(url));
/** The catalog's answer for one document, asked by its path (envelopes) or its id (its envelope). */
function catalogOf(url) {
  const parsed = new URL(url, 'http://cad.local');
  const file = parsed.searchParams.get('path') || Object.keys(IDS).find(path => IDS[path] === parsed.pathname.split('/').pop());
  const envelope = file && IDS[file] ? { id: IDS[file], kind: 'step', entry: { id: IDS[file], file }, revision: '' } : null;
  return parsed.searchParams.has('path') ? { documents: envelope ? [envelope] : [] } : envelope;
}

test('the web host keeps the URL, the history, the title and the appearance, and hands the rest to the shared viewer', async () => {
  // A link names the document by its id, in the URL's path.
  const dom = new JSDOM('<div id="root"></div>', { url: `http://cad.local/${ONE}` });
  const { window } = dom;
  let systemDark = false;
  const appearanceListeners = new Set();
  const matchMedia = () => ({ get matches() { return systemDark; }, addEventListener(_name, listener) { appearanceListeners.add(listener); }, removeEventListener(_name, listener) { appearanceListeners.delete(listener); } });
  for (const [key, value] of Object.entries({ window, document: window.document, navigator: window.navigator, localStorage: window.localStorage, sessionStorage: window.sessionStorage, matchMedia, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  window.matchMedia = matchMedia;
  const serverCalls = [];
  // The library every CAD view shares, written over this Viewer's routes.
  const libraryCalls = [];
  const guards = [];  // the header no page from another site can send, on each analytics answer
  const notice = { latest: '0.9.0', version: '0.8.1' };
  const fetchBefore = globalThis.fetch;
  globalThis.fetch = async (url, init = {}) => {
    libraryCalls.push([url, init.body ? JSON.parse(init.body) : null]);
    if (url === '/api/v1/settings' && init.body) guards.push(init.headers?.['x-cadgen-viewer']);
    const telemetry = init.body ? { share: false, reason: 'choice', policy: 'p' } : { share: false, reason: 'untold', policy: 'p' };
    const reply = isCatalog(url, init) ? catalogOf(url) : url === '/api/v1/server' ? { notice }
      : url === '/api/v1/local/update' ? { notice, release: '0.8.1', update: { state: 'working', target: '0.9.0', progress: { stage: 'install', done: 0, total: 4 } } }
      : url === '/api/v1/documents' ? { documents: [] } : url === '/api/v1/local/pick' ? { path: '/m/picked.step' }
      : url !== '/api/v1/settings' ? { ok: true }
      : { language: { locale: null }, telemetry };
    return new Response(JSON.stringify(reply), { headers: { 'content-type': 'application/json' } });
  };
  // The page's own client over this Viewer's routes, its server's description answered here.
  const client = { ...createWebCadClient({ document: window.document }), serverInfo: async options => { serverCalls.push(options); return { identityToken: 'restarted', start: '/m/launch', release: '0.9.0' }; } };
  const root = createRoot(window.document.getElementById('root'));
  const tabStore = createTabStore(sessionTabRecord(window.sessionStorage));
  const viewer = () => snapshot();
  try {
    const historyAtStart = window.history.length;
    // The update notice comes with the server's description (`main.tsx`): the button draws with the page.
    await act(() => root.render(createElement(App, { client, server: { start: '/m', pick: true, platform: 'darwin' }, tabStore, notice })));
    // The document the URL names, as it names it; the host's file menu and links; the tab's store
    // for everything the viewer keeps.
    assert.equal(viewer().file, ONE);
    assert.equal(new URL(window.location.href).pathname, `/${ONE}`);
    assert.equal(window.history.length, historyAtStart);
    assert.equal(viewer().host.files.id, 'local');
    assert.equal(viewer().tabStore, tabStore);
    assert.deepEqual(Object.keys(viewer().host.fileActions.perform).sort(), ['copy-path', 'reveal']);
    assert.equal(viewer().host.fileActions.platform, 'darwin', 'Reveal is labeled for the machine the server runs on');
    await viewer().host.fileActions.perform.reveal({ path: '/m/one.step', kind: 'file' });
    assert.deepEqual(libraryCalls.filter(([url]) => url === '/api/v1/local/reveal'), [['/api/v1/local/reveal', { path: '/m/one.step' }]]);
    assert.equal(viewer().host.links.version, '0.7.4');
    assert.equal('navigation' in viewer().host, false, 'navigation is the shared viewer\'s: the host only shows what it is asked to');
    // An engine of another release answering is an update, which the page reloads into.
    assert.deepEqual(await autoReloadOptions().fetchServerInfo(), { ok: true, identityToken: 'restarted', release: '0.9.0' });
    assert.deepEqual(serverCalls[0], { fresh: true });

    // The appearance is the tab's, resolved against the OS; its control is the app menu's Theme row,
    // over every file and on the home: the host has no light/dark button of its own.
    assert.equal(viewer().colorScheme.preference, 'system');
    assert.equal(viewer().host.environment.colorScheme, 'light');
    await act(() => { systemDark = true; for (const listener of appearanceListeners) listener(); });
    assert.equal(viewer().host.environment.colorScheme, 'dark');
    assert.equal(window.document.documentElement.classList.contains('dark'), true);
    await act(() => viewer().colorScheme.onPreferenceChange('light'));
    assert.equal(viewer().colorScheme.preference, 'light');
    assert.equal(viewer().host.environment.colorScheme, 'light');
    assert.equal(window.document.documentElement.classList.contains('dark'), false);
    // In the tab's record, under no key of its own and in no cookie.
    assert.equal(JSON.parse(window.sessionStorage.getItem(TAB_RECORD_KEY)).settings.appearance, 'light');
    assert.equal(window.localStorage.length, 0);
    assert.equal(window.document.cookie, '');

    // Once the catalog has the file, the page is named after it and it joins the library.
    await act(() => viewer().onShown('/m/one.step', ONE));
    assert.equal(window.document.title, 'one.step');
    assert.deepEqual(libraryCalls.filter(([url]) => url === '/api/v1/documents'), [['/api/v1/documents', { action: 'open', path: '/m/one.step' }]]);
    // CAD's telemetry, as the CAD app's: the person's settings read for the consent (and once for the
    // language), its answer in the app menu. (The model shown is counted, by its format and only with
    // consent, as it joins the library.)
    assert.deepEqual(libraryCalls.filter(([url]) => url.startsWith('/api/v1/settings')), [['/api/v1/settings', null], ['/api/v1/settings', null]]);
    // A Quick Edit copied is counted by this Viewer's server, as a touch is: told nothing of the edit.
    viewer().host.usage.used('quickEdit');
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(libraryCalls.filter(([url]) => url === '/api/v1/local/activity'), [['/api/v1/local/activity', { quickEdit: true }]]);
    libraryCalls.splice(libraryCalls.findIndex(([url]) => url === '/api/v1/local/activity'), 1);
    // So are the controls a person used, as the shared viewer counted them: names and seconds, nothing else.
    viewer().host.usage.controls([{ control: 'display_xray', count: 1, seconds: 0 }]);
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(libraryCalls.filter(([url]) => url === '/api/v1/local/activity'),
      [['/api/v1/local/activity', { controls: [{ control: 'display_xray', count: 1, seconds: 0 }] }]]);
    libraryCalls.splice(libraryCalls.findIndex(([url]) => url === '/api/v1/local/activity'), 1);
    // The app menu: Analytics.
    assert.deepEqual(viewer().appSettings.map(setting => [setting.label, setting.checked]),
      [['Telemetry', false]]);
    // Nothing asks (a cad command says it once): the viewer has no notice, and the app menu's toggle
    // is the person's answer.
    assert.equal(viewer().notice, undefined);
    await act(() => viewer().appSettings[0].onCheckedChange(false));
    assert.deepEqual(libraryCalls.filter(([url]) => url === '/api/v1/settings').at(-1), ['/api/v1/settings', { telemetry: { share: false } }]);
    // A newer release is the update button, as in the CAD app: an icon first in the navbar while this
    // install is behind, drawn from the notice the page started with: nothing is read for it.
    assert.equal(viewer().update.props.notice.latest, '0.9.0');
    assert.equal(viewer().update.props.phase.phase, 'idle');
    assert.deepEqual(libraryCalls.filter(([url]) => url === '/api/v1/server'), [], 'nothing read: the page started with the notice');
    // A click updates: the engine is asked, and the button follows its update.
    await act(async () => { viewer().update.props.onUpdate(); await new Promise(resolve => setTimeout(resolve, 10)); });
    assert.deepEqual(libraryCalls.filter(([url]) => url === '/api/v1/local/update').map(([url]) => url), ['/api/v1/local/update']);
    assert.equal(viewer().update.props.phase.phase, 'working');
    assert.deepEqual(guards, ['1']);

    // Showing another file is a navigation, by the file's id: pushed, and undone by Back.
    const historyLength = window.history.length;
    await act(async () => { viewer().onShow('/m/folder\\two.step'); await new Promise(resolve => setTimeout(resolve, 10)); });
    assert.equal(viewer().file, TWO);
    assert.equal(new URL(window.location.href).pathname, `/${TWO}`);
    assert.equal(window.history.length, historyLength + 1);
    await act(async () => { viewer().onShow('/m/folder/two.step'); await new Promise(resolve => setTimeout(resolve, 10)); });
    assert.equal(window.history.length, historyLength + 1, 'the file on screen is no navigation at all');
    await act(() => { window.history.replaceState({}, '', `/${ONE}`); window.dispatchEvent(new window.PopStateEvent('popstate')); });
    assert.equal(viewer().file, ONE);
    // A URL that names no document shows the home: the library every CAD view shares, Open, and
    // the folder of the most recent launch, read again from the server.
    await act(async () => { window.history.replaceState({}, '', '/'); window.dispatchEvent(new window.PopStateEvent('popstate')); await new Promise(resolve => setTimeout(resolve, 10)); });
    assert.equal(viewer().file, '');
    await act(() => viewer().onShown(null));
    assert.equal(window.document.title, 'text-to-cad');
    assert.deepEqual(await viewer().library.list(), []);
    assert.equal(libraryCalls.at(-1)[0], '/api/v1/documents');
    // A picture, by its document's id, versioned by its name.
    assert.equal(await viewer().library.thumbnail({ id: ONE, thumbnail: 'abc.png' }), `/api/v1/documents/${ONE}/thumbnail?v=abc.png`);
    // A model opened from the home, and one picked with Open, are shown here, each a new step.
    await act(() => viewer().library.open({ path: '/m/folder/two.step' }));
    assert.equal(viewer().file, TWO);
    await act(() => viewer().library.pick());
    assert.ok(libraryCalls.some(([url]) => url === '/api/v1/local/pick'));
    assert.equal(viewer().file, PICKED);
    assert.equal(new URL(window.location.href).pathname, `/${PICKED}`);
    // Back to home leads to the bare URL: the home is a step of the browser's history, as a file is,
    // so the browser's Back and Forward walk between them (the page hands no history of its own).
    const beforeHome = window.history.length;
    await act(async () => { viewer().onShow(''); await new Promise(resolve => setTimeout(resolve, 10)); });
    assert.equal(new URL(window.location.href).pathname, '/');
    assert.equal(new URL(window.location.href).search, '');
    assert.equal(window.history.length, beforeHome + 1);
    assert.equal(viewer().history, undefined);
  } finally {
    globalThis.fetch = fetchBefore;
    await act(() => root.unmount());
    assert.equal(appearanceListeners.size, 0);
    dom.window.close();
  }
});

test('a page whose engine is gone says so in its language, over the page, until the engine answers', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: `http://cad.local/${ONE}` });
  const { window } = dom;
  const matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  for (const [key, value] of Object.entries({ window, document: window.document, navigator: window.navigator, localStorage: window.localStorage, sessionStorage: window.sessionStorage, matchMedia, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  window.matchMedia = matchMedia;
  const fetchBefore = globalThis.fetch;
  // The catalog's answer: nothing listening (a stopped engine), an engine that does not know this
  // page's token (one started since), or the engine back.
  let catalog = 'back';
  globalThis.fetch = async (url, init = {}) => {
    if (isCatalog(url, init) && catalog === 'stopped') throw new TypeError('Failed to fetch');
    if (isCatalog(url, init) && catalog === 'restarted') {
      return new Response(JSON.stringify({ error: 'engine token required' }), { status: 403, headers: { 'content-type': 'application/json' } });
    }
    const reply = isCatalog(url, init) ? catalogOf(url) : url === '/api/v1/documents' ? { documents: [] }
      : url === '/api/v1/settings' ? { language: { locale: 'ja' }, telemetry: { share: false, reason: 'untold', policy: 'p' } } : { ok: true };
    return new Response(JSON.stringify(reply), { headers: { 'content-type': 'application/json' } });
  };
  const client = { ...createWebCadClient({ document: window.document }), serverInfo: async () => ({ start: '/m' }) };
  const root = createRoot(window.document.getElementById('root'));
  const alert = () => window.document.querySelector('[role="alert"]');
  try {
    await act(() => root.render(createElement(App, { client, server: { start: '/m' }, tabStore: createTabStore(sessionTabRecord(window.sessionStorage)), language: 'ja' })));
    await act(() => client.refresh({ file: ONE }));
    assert.equal(alert() === null, true, 'nothing is said while the engine answers');
    catalog = 'stopped';
    await act(() => client.refresh({ file: ONE }).catch(() => {}));
    assert.match(alert()?.textContent ?? '', /CAD が動いていません。/);
    assert.match(alert()?.textContent ?? '', /次にエージェントが CAD を使うか、CAD アプリを開くと再び起動します。/);
    // The one notice: the page under it, a view's own card among it, is out of reach and unheard.
    assert.equal(window.document.querySelectorAll('[role="alert"]').length, 1);
    const under = alert()?.nextElementSibling;
    assert.deepEqual([under?.hasAttribute('inert'), under?.getAttribute('aria-hidden')], [true, 'true']);
    assert.doesNotMatch(alert()?.textContent ?? '', /Failed to fetch|\{/, 'never the failure itself');
    assert.equal(snapshot() !== undefined, true, 'the page stays under it');
    catalog = 'restarted';
    await act(() => client.refresh({ file: ONE }).catch(() => {}));
    // An engine that refuses the token runs: the page's link was replaced (`cad server --rotate-token`).
    assert.match(alert()?.textContent ?? '', /このリンクは使えなくなりました。/);
    assert.match(alert()?.textContent ?? '', /エージェントにもう一度モデルを開いてもらい、新しいリンクを使ってください。/);
    assert.doesNotMatch(alert()?.textContent ?? '', /engine token required|エンジンが動いていません/);
    catalog = 'back';
    await act(() => client.refresh({ file: ONE }));
    assert.equal(alert() === null, true, 'gone with the first read that answers');
    assert.equal(window.document.querySelector('[inert]'), null, 'the page in reach again');
  } finally {
    globalThis.fetch = fetchBefore;
    await act(() => root.unmount());
    client.dispose();
    dom.window.close();
  }
});

test('the notice says the page reconnects, and how to start the engine', async () => {
  const dom = new JSDOM('<div id="root"></div>');
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
  const root = createRoot(dom.window.document.getElementById('root'));
  try {
    await act(() => root.render(createElement(EngineStopped, { locale: 'en' })));
    assert.equal(dom.window.document.querySelector('[role="alert"]')?.textContent,
      'CAD is not running.It starts again when your agent next uses CAD or you open the CAD app; this page reconnects on its own.Reload');
    await act(() => root.render(createElement(EngineStopped, { locale: 'en', refused: true })));
    assert.equal(dom.window.document.querySelector('[role="alert"]')?.textContent,
      "This link no longer works.Ask your agent to open the model again and use the new link.");
  } finally {
    await act(() => root.unmount());
    dom.window.close();
  }
});
