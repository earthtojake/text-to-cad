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
const temporary = await mkdtemp(join(tmpdir(), 'text-to-cad-web-share-'));
const output = join(temporary, 'share.mjs');
await build({
  stdin: { contents: `export {ShareFailed, ShareDelete} from './SharePage.tsx'; export {SHARE_GONE} from './host/share.js';
    export {SHARE_DAMAGED, SHARE_UNAVAILABLE, SHARE_UNSUPPORTED} from '@cad/core/client'; export {translateIn} from '@cad/ui/i18n';
    export {act,createElement} from 'react'; export {createRoot} from 'react-dom/client';`, resolveDir: fileURLToPath(new URL('.', import.meta.url)) },
  bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', outfile: output, loader: { '.css': 'empty', '.svg': 'dataurl' },
  banner: { js: `import {createRequire} from 'node:module'; const require=createRequire(import.meta.url);` },
  plugins: [{ name: 'react-external', setup(plugin) {
    plugin.onResolve({ filter: /^react(?:\/|$)|^react-dom(?:\/|$)/ }, args => ({
      path: args.kind.startsWith('require') ? require.resolve(args.path) : pathToFileURL(require.resolve(args.path)).href,
      external: true,
    }));
  } }],
});
const { ShareFailed, ShareDelete, SHARE_GONE, SHARE_DAMAGED, SHARE_UNAVAILABLE, SHARE_UNSUPPORTED, translateIn, act, createElement, createRoot } =
  await import(pathToFileURL(output).href);
after(() => rm(temporary, { recursive: true, force: true }));

const { window } = new JSDOM('<div id="root"></div>', { url: 'https://cad.example/AbCdEfGhIjKlMnOpQrSt_-' });
for (const [key, value] of Object.entries({ window, document: window.document, navigator: window.navigator, HTMLElement: window.HTMLElement,
  Element: window.Element, Node: window.Node, IS_REACT_ACT_ENVIRONMENT: true })) {
  Object.defineProperty(globalThis, key, { configurable: true, writable: true, value });
}
const say = key => translateIn('en', key);

/** The page a share's view says `error` with: its state, its title and explanation, and its one action, if any. */
async function failed(error) {
  const element = window.document.createElement('div');
  window.document.body.append(element);
  const root = createRoot(element);
  let retried = 0;
  await act(() => root.render(createElement(ShareFailed, { error, locale: 'en', onRetry: () => { retried += 1; } })));
  const page = element.querySelector('[data-share-state]');
  const [title, detail] = [...page.querySelectorAll('[data-status-screen] p')].map(line => line.textContent);
  const action = page.querySelector('button');
  if (action) await act(() => action.click());
  await act(() => root.unmount());
  element.remove();
  return { state: page.dataset.shareState, alert: page.getAttribute('role') === 'alert', title, detail, action: action?.textContent ?? null, retried };
}
const coded = (code, message) => Object.assign(new Error(message), { code });

test("a shared model's view that did not open says why: gone, a damaged link, a form it does not read, or anything else with Retry", async () => {
  // Gone: the service has none (404), which lasts: no action, and the rule that a share lasts 7 days.
  assert.deepEqual(await failed(coded(SHARE_GONE, 'This shared model has expired or was deleted.')),
    { state: 'gone', alert: true, title: say('share.gone.title'), detail: say('share.gone.detail'), action: null, retried: 0 });
  // A damaged link (a manifest that does not open or is not one, a file not as it says): nothing to retry.
  assert.deepEqual(await failed(coded(SHARE_DAMAGED, 'This link is damaged: the share\'s manifest does not open.')),
    { state: 'damaged', alert: true, title: say('share.damaged.title'), detail: say('share.damaged.detail'), action: null, retried: 0 });
  // A bundle this viewer does not open says which.
  const unsupported = await failed(coded(SHARE_UNSUPPORTED, 'This shared model holds no view bundle this viewer opens: view-bundle/9.'));
  assert.deepEqual(unsupported, { state: 'unsupported', alert: true, title: say('share.unsupported.title'),
    detail: 'This shared model holds no view bundle this viewer opens: view-bundle/9.', action: null, retried: 0 });
  // Anything else may pass: a pack that did not come, a refusal, no network. It says what, and offers Retry.
  for (const error of [coded(SHARE_UNAVAILABLE, "This shared model's manifest.json could not be fetched: Failed to fetch"),
    Object.assign(new Error('The share service answered 429 to the shared model\'s request: Too many requests.'), { status: 429 }),
    new TypeError('Failed to fetch')]) {
    assert.deepEqual(await failed(error), { state: 'failed', alert: true, title: say('share.failed.title'), detail: error.message,
      action: say('share.retry'), retried: 1 }, error.message);
  }
});

test("a delete link that cuts its secret short says so, and offers nothing to send", async () => {
  const element = window.document.createElement('div');
  window.document.body.append(element);
  const root = createRoot(element);
  await act(() => root.render(createElement(ShareDelete, { id: 'AbCdEfGhIjKlMnOpQrSt_-', secret: 'cut-short', locale: 'en' })));
  const page = element.querySelector('[data-share-state]');
  const [title, detail] = [...page.querySelectorAll('[data-status-screen] p')].map(line => line.textContent);
  assert.deepEqual({ state: page.dataset.shareState, title, detail, action: page.querySelector('button') },
    { state: 'damaged', title: say('share.delete.damaged.title'), detail: say('share.delete.damaged.detail'), action: null });
  await act(() => root.unmount());
  element.remove();
});
