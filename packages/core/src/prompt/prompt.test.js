import test from 'node:test';
import assert from 'node:assert/strict';
import { annotationPart, formatPromptAnnotation, createPromptContext, createPromptDeliveryLedger, referencePart, textPart, validatePromptContext, formatPromptContextText, formatPromptReference } from './index.js';

const reference = { resource: { kind: 'workspace-file', workspaceId: 'root', path: 'STEP/my part.step', revision: 'v1' }, target: { kind: 'cad-selector', selectors: ['o1.2.f45'] } };
test('one context retains image/reference relationships and formats canonical references', () => {
  const capture = Promise.resolve(new Blob(['png'], { type: 'image/png' }));
  const context = createPromptContext([referencePart(reference, 'face'), { id: 'image', kind: 'attachment', name: 'view.png', mimeType: 'image/png', content: capture, about: ['face'] }, textPart('Increase the clearance.')]);
  assert.equal(validatePromptContext(context), context);
  assert.equal(context.parts[1].content, capture);
  assert.equal(formatPromptContextText(context), '"STEP/my part.step"#o1.2.f45\nIncrease the clearance.');
  assert.notEqual(createPromptContext([textPart('next')]).operationId, context.operationId);
});
test('code targets preserve explicit ranges rather than borrowing the CAD fragment grammar', () => {
  const code = { resource: { kind: 'workspace-file', workspaceId: 'root', path: 'src/bracket.py' }, target: { kind: 'text-range', start: { line: 4, character: 2 }, end: { line: 6, character: 0 } } };
  assert.equal(formatPromptReference(code), 'src/bracket.py:5:3-7:1');
  assert.equal(formatPromptReference(code, { resolvePath: r => `/project/${r.path}` }), '/project/src/bracket.py:5:3-7:1');
});
test('invalid bundles fail before delivery, including dangling relationships and unknown targets', () => {
  assert.throws(() => createPromptContext([textPart('a'), textPart('b')]), /unique/);
  assert.throws(() => createPromptContext([{ id: 'i', kind: 'attachment', name: 'a.pdf', mimeType: 'application/pdf', content: new Blob(), about: ['missing'] }]), /absent reference/);
  assert.throws(() => referencePart({ ...reference, target: { kind: 'guess' } }), /unknown reference/);
  assert.throws(() => referencePart({ ...reference, resource: { ...reference.resource, path: '../outside.step' } }), /root-relative/);
  assert.throws(() => referencePart({ ...reference, target: { kind: 'cad-selector', selectors: ['#not valid'] } }), /invalid CAD/);
});
test('a delivery ledger delivers each operation once, bounds work in flight, and forgets what failed', async () => {
  const ledger = createPromptDeliveryLedger({ maxPending: 2, maxRemembered: 3, busyMessage: 'busy' });
  let starts = 0;
  const release = [];
  const held = () => { starts += 1; return new Promise(resolve => release.push(() => resolve({ status: 'copied', partIds: [] }))); };
  const first = ledger.deliver('a', held);
  assert.equal(ledger.deliver('a', held), first, 'a repeated operation is the one already on its way');
  ledger.deliver('b', held);
  assert.deepEqual(await ledger.deliver('c', held), { status: 'failed', message: 'busy' });
  assert.equal(starts, 2);
  release.forEach(done => done());
  assert.deepEqual(await first, { status: 'copied', partIds: [] });
  assert.equal(ledger.deliver('a', held), first, 'and a delivered one is remembered');
  // A throw or a rejection is a failure, and a failure is forgotten so it can be retried.
  assert.deepEqual(await ledger.deliver('d', () => { throw new Error('no clipboard'); }), { status: 'failed', message: 'no clipboard' });
  await new Promise(resolve => setTimeout(resolve));
  assert.deepEqual(await ledger.deliver('d', () => ({ status: 'added', partIds: ['x'] })), { status: 'added', partIds: ['x'] });
  // Memory is bounded: completed operations make room.
  for (const id of ['e', 'f', 'g']) await ledger.deliver(id, () => ({ status: 'copied', partIds: [] }));
  let restarted = 0;
  await ledger.deliver('a', () => { restarted += 1; return { status: 'copied', partIds: [] }; });
  assert.equal(restarted, 1, 'the oldest completed operation was evicted');
});

test('an annotation carries the geometry it is about and the note, and reads as one line', () => {
  const resource = { kind: 'workspace-file', workspaceId: 'w', path: 'parts/bracket.step' };
  const edge = { resource, target: { kind: 'cad-selector', selectors: ['o1.1.e3'] }, label: 'Edge 3' };
  const context = createPromptContext([annotationPart([edge], 'make a hole in it', 'a1')]);
  assert.ok(Object.isFrozen(context.parts[0].references[0].target.selectors));
  assert.equal(formatPromptContextText(context), 'parts/bracket.step#o1.1.e3: make a hole in it');
  assert.equal(formatPromptAnnotation(context.parts[0], { labels: true }), 'parts/bracket.step#o1.1.e3 (Edge 3): make a hole in it');
  assert.throws(() => createPromptContext([{ id: 'a', kind: 'annotation', references: [], text: 'x' }]), /at least one reference/);
  assert.throws(() => createPromptContext([{ id: 'a', kind: 'annotation', references: [edge] }]), /its note/);
});

test('an annotation on a markup names the attachment the markup is in', () => {
  const resource = { kind: 'workspace-file', workspaceId: 'w', path: 'drawings/clip.pdf' };
  const page = { resource, target: { kind: 'whole-resource' }, label: 'clip.pdf, page 2' };
  const image = { id: 'markup', kind: 'attachment', name: 'markup.png', mimeType: 'image/png', content: Promise.resolve(new Blob(['png'], { type: 'image/png' })) };
  const context = createPromptContext([image, annotationPart([page], 'move this dimension off the hole', 'a1', { attachment: 'markup' })]);
  assert.equal(context.parts[1].attachment, 'markup');
  assert.throws(() => createPromptContext([annotationPart([page], 'x', 'a1', { attachment: 'missing' })]), /absent attachment/);
});
