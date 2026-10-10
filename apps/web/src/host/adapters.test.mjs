import assert from 'node:assert/strict';
import { after, test } from 'node:test';
import { build } from 'esbuild';
import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const temporary = await mkdtemp(join(tmpdir(), 'web-host-adapters-'));
const output = join(temporary, 'adapters.mjs');
await build({
  stdin: { contents: `export {createWebPromptContext} from './promptContext.ts';export {browserClipboard} from './clipboard.ts';export {createBroadcastCrossProbe} from './crossProbe.ts';`, resolveDir: fileURLToPath(new URL('.', import.meta.url)) },
  bundle: true, platform: 'node', format: 'esm', outfile: output,
});
const { createWebPromptContext, browserClipboard, createBroadcastCrossProbe } = await import(pathToFileURL(output).href);
after(() => rm(temporary, { recursive: true, force: true }));
const reference = { id: 'ref', kind: 'reference', reference: { resource: { kind: 'workspace-file', path: '/Car project/folder/part.step', revision: 'r4' }, target: { kind: 'cad-selector', selectors: ['o1.f2'] } } };
const context = (operationId, parts) => ({ schemaVersion: 1, operationId, parts });
function replaceGlobal(name, value) {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, name);
  Object.defineProperty(globalThis, name, { configurable: true, value });
  return () => descriptor ? Object.defineProperty(globalThis, name, descriptor) : delete globalThis[name];
}

test('web references name the file by its absolute path, in ordered plain text, with duplicate delivery suppressed', async () => {
  const writes = [];
  const clipboard = { writeText: async text => writes.push(text) };
  const port = createWebPromptContext(clipboard);
  const bundle = context('text', [{ id: 'intro', kind: 'text', text: 'Inspect this face' }, reference]);
  const result = await port.deliver(bundle);
  assert.deepEqual(result, { status: 'copied', partIds: ['intro', 'ref'] });
  assert.deepEqual(await port.deliver(bundle), result);
  assert.deepEqual(writes, ['Inspect this face\n"/Car project/folder/part.step"#o1.f2']);
});

test('browser mixed copy starts within the gesture and reports separate representations truthfully', async () => {
  const events = [];
  let resolve;
  const image = new Promise(done => { resolve = done; });
  class Item { constructor(content) { this.content = content; events.push('item'); } }
  const restoreItem = replaceGlobal('ClipboardItem', Item);
  const restoreNavigator = replaceGlobal('navigator', { clipboard: { write: async items => {
    events.push('write');
    assert.equal(await items[0].content['text/plain'].text(), '"/Car project/folder/part.step"#o1.f2');
    assert.equal(typeof items[0].content['image/png'].then, 'function');
    await items[0].content['image/png'];
    events.push('encoded');
  } } });
  try {
    const port = createWebPromptContext(browserClipboard);
    const delivered = port.deliver(context('mixed', [reference, { id: 'png', kind: 'attachment', name: 'view.png', mimeType: 'image/png', content: image, about: ['ref'] }]));
    assert.deepEqual(events, ['item', 'write']);
    resolve(new Blob(['encoded'], { type: 'image/png' }));
    const result = await delivered;
    assert.equal(result.status, 'partial');
    assert.deepEqual(result.partIds, ['ref', 'png']);
    assert.match(result.message, /Some apps paste only one/);
    assert.deepEqual(events, ['item', 'write', 'encoded']);
  } finally { restoreNavigator(); restoreItem(); }
});

test('unsupported mixed clipboard and arbitrary attachments fail without silently copying a subset', async () => {
  const writes = [];
  const clipboard = { writeText: async text => writes.push(text), writeImage: async image => writes.push(image) };
  const port = createWebPromptContext(clipboard);
  const attachment = { id: 'png', kind: 'attachment', name: 'view.png', mimeType: 'image/png', content: new Blob(['png'], { type: 'image/png' }) };
  assert.equal((await port.deliver(context('mixed-unsupported', [reference, attachment]))).status, 'failed');
  assert.equal((await port.deliver(context('binary', [reference, { ...attachment, mimeType: 'application/zip' }]))).status, 'failed');
  assert.deepEqual(writes, []);
});

test('permission or encoder failure returns failed rather than copied', async () => {
  let attempts = 0;
  const port = createWebPromptContext({ writeText: async () => { if (!attempts++) throw new Error('Permission denied'); } });
  assert.deepEqual(await port.deliver(context('denied', [reference])), { status: 'failed', message: 'Permission denied' });
  assert.deepEqual(await port.deliver(context('denied', [reference])), { status: 'copied', partIds: ['ref'] });
  assert.equal(attempts, 2);
});


test('viewport PNG copy uses the guarded local endpoint without browser clipboard permission', async () => {
  const calls = [];
  const restore = replaceGlobal('fetch', async (...args) => { calls.push(args); return {ok:true}; });
  try {
    const png = new Blob(['png'], {type:'image/png'});
    await browserClipboard.writeImage(Promise.resolve(png));
    assert.equal(calls[0][0], '/__cad/clipboard');
    assert.equal(calls[0][1].headers['x-cadgen-viewer'], '1');
    assert.equal(calls[0][1].body, png);
  } finally { restore(); }
});

test('cross-probing reaches the other viewer pages, never the page that selected, and closes with its last listener', async () => {
  // Two pages' ports on one channel (a name of this test's own), as a board's window and its schematic's.
  const name = `cross-probe-test-${process.pid}`;
  const board = createBroadcastCrossProbe(name);
  const schematic = createBroadcastCrossProbe(name);
  const heardByBoard = [];
  const heardBySchematic = [];
  const stopBoard = board.subscribe(message => heardByBoard.push(message));
  const stopSchematic = schematic.subscribe(message => heardBySchematic.push(message));
  const until = async (done) => { while (!done()) await new Promise(resolve => setImmediate(resolve)); };
  board.publish({ project: '/models/blinky', from: 'board', selectors: ['#U3.9'] });
  await until(() => heardBySchematic.length === 1);
  assert.deepEqual(heardBySchematic, [{ project: '/models/blinky', from: 'board', selectors: ['#U3.9'] }]);
  assert.deepEqual(heardByBoard, [], 'a page does not hear itself');
  stopSchematic();
  board.publish({ project: '/models/blinky', from: 'board', selectors: [] });
  schematic.publish({ project: '/models/blinky', from: 'schematic', selectors: ['#net:VIN'] });
  await until(() => heardByBoard.length === 1);
  assert.equal(heardBySchematic.length, 1, 'unsubscribed, the schematic hears nothing more');
  // The last listener gone, each page's channel is closed: this process can end.
  stopBoard();
  const restore = replaceGlobal('BroadcastChannel', undefined);
  try { assert.equal(createBroadcastCrossProbe(name), undefined, 'without BroadcastChannel there is no cross-probing'); } finally { restore(); }
});
