import assert from 'node:assert/strict';
import fs from 'node:fs';
import { SourceMap } from 'node:module';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { loadWithMap, packageSourceMaps } from './source-maps.mjs';

// This package as its build left it (the test runs after `npm run build`).
const root = fileURLToPath(new URL('..', import.meta.url));
const dist = path.join(root, 'dist');
const src = path.join(root, 'src');

// The line and column (0-based) at which `needle` starts in `text`.
function placeOf(text, needle) {
  const before = text.slice(0, text.indexOf(needle)).split('\n');
  return [before.length - 1, before.at(-1).length];
}

test('a compiled module loads with the map that sends it back to its source, with the source text', () => {
  const source = path.join(src, 'client/crash.js');
  const { code, map } = loadWithMap(path.join(dist, 'client/crash.js'), dist, src);
  assert.doesNotMatch(code, /sourceMappingURL/);
  assert.deepEqual(map.sources, [source]);
  assert.equal(map.sourcesContent[0], fs.readFileSync(source, 'utf8'));
  // The crash signature's test for a Chromium stack, the code a page crash's probe frame named in PostHog.
  const signature = '/^\\s+at /';
  const found = new SourceMap(map).findEntry(...placeOf(code, signature));
  assert.deepEqual([found.originalSource, found.originalLine, found.originalColumn],
    [source, ...placeOf(map.sourcesContent[0], signature)]);
});

test('a module the build copied as it is loads as its source, line for line and column for column', () => {
  const source = path.join(src, 'common/stepTopology.mjs');
  const { code, map } = loadWithMap(path.join(dist, 'common/stepTopology.mjs'), dist, src);
  assert.equal(code, fs.readFileSync(source, 'utf8'));
  const lines = code.trimEnd().split('\n');
  const last = [lines.length - 1, lines.at(-1).length - 1];
  for (const [line, column] of [[0, 0], placeOf(code, 'export function'), last]) {
    const found = new SourceMap(map).findEntry(line, column);
    assert.deepEqual([found.originalSource, found.originalLine, found.originalColumn], [source, line, column]);
  }
});

test("a page's build fails when a chunk's map still ends in a package's compiled code", () => {
  const plugin = packageSourceMaps(['@text-to-cad/core']);
  plugin.configResolved({ root });
  const out = path.join(root, 'tmp-out');
  const chunk = sources => ({ type: 'chunk', fileName: 'assets/index-A.js', map: { sources } });
  const fail = message => { throw new Error(message); };
  const relative = file => path.relative(path.join(out, 'assets'), file).split(path.sep).join('/');
  // Its source, and an image a module imports (no frame is ever in one), pass.
  plugin.generateBundle.handler.call({ error: fail }, { dir: out },
    { 'index-A.js': chunk([relative(path.join(src, 'client/crash.js')), relative(path.join(dist, 'logo.svg'))]) });
  assert.throws(() => plugin.generateBundle.handler.call({ error: fail }, { dir: out },
    { 'index-A.js': chunk([relative(path.join(dist, 'client/crash.js'))]) }),
  /assets\/index-A\.js: @text-to-cad\/core\/dist\/client\/crash\.js/);
});
