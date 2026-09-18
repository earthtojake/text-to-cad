import test from 'node:test';
import assert from 'node:assert/strict';
import { emptyDrawingDocument, parseDrawingScene, MAX_DRAWING_BYTES } from './index.js';
const rectangle = { id: 'one', type: 'rectangle', x: 10, y: 20, width: 120, height: 60 };
const scene = (patch = {}) => JSON.stringify({ ...emptyDrawingDocument(), elements: [rectangle], ...patch });
test('drawing documents round trip with embedded images and viewport, excluding host state', () => {
  const result = parseDrawingScene(scene({ files: { pic: { id: 'pic', mimeType: 'image/png', dataURL: 'data:image/png;base64,aGVsbG8=', created: 5 } },
    appState: { scrollX: 20, scrollY: 40, zoom: { value: 1.5 }, fileHandle: '/secret', collaborators: {}, viewBackgroundColor: '#eee' } }));
  assert.equal(result.files.pic.created, 5);
  assert.deepEqual(result.appState, { viewBackgroundColor: '#eee', scrollX: 20, scrollY: 40, zoom: { value: 1.5 } });
  assert.deepEqual(parseDrawingScene(JSON.stringify(result)), result);
});
test('drawing input rejects malformed scenes, huge data, duplicate ids and non-finite coordinates', () => {
  for (const value of ['null', '{}', 'not json', scene({ version: 1 }), scene({ elements: [rectangle, rectangle] }),
    scene({ elements: [{ ...rectangle, x: 1e308 }] }), scene({ elements: [{ ...rectangle, type: 'freedraw', points: [[1, 'two']] }] })]) {
    assert.throws(() => parseDrawingScene(value));
  }
  assert.throws(() => parseDrawingScene(' '.repeat(MAX_DRAWING_BYTES + 1)), /20 MiB/);
});
test('documents cannot load remote images, embedded web pages, or carry navigation links', () => {
  assert.throws(() => parseDrawingScene(scene({ elements: [{ ...rectangle, type: 'embeddable' }] })), /unsupported/);
  assert.throws(() => parseDrawingScene(scene({ files: { pic: { id: 'pic', mimeType: 'image/png', dataURL: 'https://example.com/private.png' } } })), /embedded/);
  const doc = parseDrawingScene(scene({ elements: [{ ...rectangle, link: 'https://example.com', customData: { url: 'bad' } }] }));
  assert.equal(doc.elements[0].link, null);
  assert.equal(doc.elements[0].customData, undefined);
});
