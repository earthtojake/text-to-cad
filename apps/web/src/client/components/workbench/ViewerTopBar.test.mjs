import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { build } from 'esbuild';
import { createRequire } from 'node:module';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);
const temporary = await mkdtemp(join(tmpdir(), 'hardcore-appearance-'));
const output = join(temporary, 'appearance.mjs');
after(() => rm(temporary, { recursive: true, force: true }));
await build({
  stdin: { contents: `export {default as ViewerTopBar} from './ViewerTopBar.jsx'; export {createElement} from 'react'; export {renderToStaticMarkup} from 'react-dom/server';`, resolveDir: fileURLToPath(new URL('.', import.meta.url)) },
  bundle: true, platform: 'node', format: 'esm', jsx: 'automatic', outfile: output,
  banner: { js: `import {createRequire} from 'node:module'; const require=createRequire(import.meta.url);` },
  loader: { '.ico': 'dataurl' },
  plugins: [{ name: 'appearance-test', setup(plugin) {
    plugin.onResolve({ filter: /^react(?:\/|$)|^react-dom(?:\/|$)/ }, args => ({
      path: args.kind.startsWith('require') ? require.resolve(args.path) : pathToFileURL(require.resolve(args.path)).href,
      external: true,
    }));
    // Release/network controls are unrelated to the actual appearance button.
    plugin.onResolve({ filter: /^\.\/ViewerLinks$/ }, () => ({ path: 'links', namespace: 'test-links' }));
    plugin.onLoad({ filter: /.*/, namespace: 'test-links' }, () => ({ contents: 'export default function ViewerLinks(){ return null; }', loader: 'js' }));
  } }],
});
const { ViewerTopBar, createElement, renderToStaticMarkup } = await import(pathToFileURL(output).href);

test('appearance button shows the resolved sun or moon while preserving its selected preference label', () => {
  for (const [preference, resolved, icon] of [
    ['system', 'light', 'sun'], ['system', 'dark', 'moon'],
    ['light', 'light', 'sun'], ['dark', 'dark', 'moon'],
  ]) {
    const markup = renderToStaticMarkup(createElement(ViewerTopBar, {
      colorSchemePreference: preference, resolvedColorSchemeMode: resolved,
    }));
    assert.match(markup, new RegExp(`lucide-${icon}(?: |")`));
    assert.doesNotMatch(markup, /lucide-monitor/);
    assert.match(markup, new RegExp(`aria-label="Appearance: ${preference[0].toUpperCase()}${preference.slice(1)}"`));
  }
});
