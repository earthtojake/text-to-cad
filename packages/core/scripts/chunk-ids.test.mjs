import assert from 'node:assert/strict';
import test from 'node:test';

import { stampDebugId } from './chunk-ids.mjs';

const BUNDLERS = '2974902c-c21f-457c-bb5a-8b71d7a9d3ef';
const chunk = code => `${code}\n//# debugId=${BUNDLERS}\n`;
const map = sources => JSON.stringify({ version: 3, sources, mappings: 'AAAA', debugId: BUNDLERS });

test('one debug id names one chunk text with one map', () => {
  const viewer = stampDebugId(chunk('import"./a.js";f()'), map(['a.ts']));
  // The CAD app's copy of that chunk, its import rewritten, and the same code with the map of a source
  // that moved: the bundler named all three alike, and PostHog would keep one map for them.
  const app = stampDebugId(chunk('import"cad-chunk:a.js";f()'), map(['a.ts']));
  const moved = stampDebugId(chunk('import"./a.js";f()'), map(['b.ts']));
  assert.equal(new Set([BUNDLERS, viewer.debugId, app.debugId, moved.debugId]).size, 4);
  // The same text and map, the same id: a rebuild, or a release that ships the chunk again, uploads it once.
  assert.deepEqual(stampDebugId(chunk('import"./a.js";f()'), map(['a.ts'])), viewer);
  assert.match(viewer.debugId, /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
  // Only the closing line changes, so no code moves; the map names the new id too.
  assert.equal(viewer.code, chunk('import"./a.js";f()').replace(BUNDLERS, viewer.debugId));
  assert.equal(JSON.parse(viewer.map).debugId, viewer.debugId);
});

test('a chunk that does not end with its debug id line is refused', () => {
  assert.throws(() => stampDebugId('f()', map(['a.ts']), 'index-A.js'), /index-A\.js does not end with/);
});
