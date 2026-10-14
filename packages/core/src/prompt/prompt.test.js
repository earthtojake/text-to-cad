import test from 'node:test';
import assert from 'node:assert/strict';
import { createPromptContext, createPromptDeliveryLedger, referencePart, textPart, validatePromptContext, formatPromptContextText, formatPromptMessage, formatPromptReference, promptReferenceIds } from './index.js';

const reference = { resource: { kind: 'workspace-file', path: '/work/STEP/my part.step', revision: 'v1' }, target: { kind: 'cad-selector', selectors: ['o1.2.f45'] } };
test('one context retains image/reference relationships and formats canonical references', () => {
  const capture = Promise.resolve(new Blob(['png'], { type: 'image/png' }));
  const context = createPromptContext([referencePart(reference, 'face'), { id: 'image', kind: 'attachment', name: 'view.png', mimeType: 'image/png', content: capture, about: ['face'] }, textPart('Increase the clearance.')]);
  assert.equal(validatePromptContext(context), context);
  assert.equal(context.parts[1].content, capture);
  assert.equal(formatPromptContextText(context), '"/work/STEP/my part.step"#o1.2.f45\nIncrease the clearance.');
  assert.notEqual(createPromptContext([textPart('next')]).operationId, context.operationId);
});
test('a message says what the person wrote, then the file, its references and a picture saved as a file', () => {
  const file = { resource: reference.resource, target: { kind: 'whole-resource' } };
  const sketch = { id: 'sketch', kind: 'attachment', name: 'part-sketch.png', mimeType: 'image/png', content: new Blob(), about: ['file'], label: 'Sketch' };
  const context = createPromptContext([textPart('Round this edge.\n'), referencePart(file, 'file'), referencePart(reference, 'face'), sketch]);
  assert.equal(formatPromptMessage(context, { attachmentPath: part => `/tmp/${part.name}` }),
    'Round this edge.\n\nFile: "/work/STEP/my part.step"\nReferences:\n"/work/STEP/my part.step"#o1.2.f45\nSketch: /tmp/part-sketch.png');
  // A picture sent beside the text is not named in it.
  assert.equal(formatPromptMessage(createPromptContext([textPart('Why?'), referencePart(file, 'file'), sketch])), 'Why?\n\nFile: "/work/STEP/my part.step"');
});
test('code targets preserve explicit ranges rather than borrowing the CAD fragment grammar', () => {
  const code = { resource: { kind: 'workspace-file', path: '/work/src/bracket.py' }, target: { kind: 'text-range', start: { line: 4, character: 2 }, end: { line: 6, character: 0 } } };
  assert.equal(formatPromptReference(code), '/work/src/bracket.py:5:3-7:1');
});
test('a reference names its ids as a person reads them: each selector, a range from 1, or its label', () => {
  assert.deepEqual(promptReferenceIds({ ...reference, target: { kind: 'cad-selector', selectors: ['o1.f2', 'o1.e3'] } }), ['o1.f2', 'o1.e3']);
  const range = { resource: { kind: 'workspace-file', path: '/work/a.py' }, target: { kind: 'text-range', start: { line: 0, character: 4 }, end: { line: 2, character: 0 } } };
  assert.deepEqual(promptReferenceIds(range), ['1:5–3:1']);
  assert.deepEqual(promptReferenceIds({ ...range, label: 'def plate' }), ['def plate']);
  assert.deepEqual(promptReferenceIds({ ...range, target: { kind: 'whole-resource' } }), []);
});

test('invalid bundles fail before delivery, including dangling relationships and unknown targets', () => {
  assert.throws(() => createPromptContext([textPart('a'), textPart('b')]), /unique/);
  assert.throws(() => createPromptContext([{ id: 'i', kind: 'attachment', name: 'a.pdf', mimeType: 'application/pdf', content: new Blob(), about: ['missing'] }]), /absent reference/);
  assert.throws(() => referencePart({ ...reference, target: { kind: 'guess' } }), /unknown reference/);
  for (const path of ['STEP/relative.step', '/work/../outside.step', 'C:\\work\\a.step']) assert.throws(() => referencePart({ ...reference, resource: { ...reference.resource, path } }), /absolute/);
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

test('a selection with a summary reads its summary, then its references', () => {
  const summarized = { resource: { kind: 'workspace-file', path: '/work/bracket.step' }, target: { kind: 'cad-selector', selectors: ['o1.f3', 'o1.f1'] },
    summary: 'The peak stress, 120 MPa, is above the 100 MPa this material yields at' };
  assert.equal(formatPromptMessage(createPromptContext([textPart('fix this'), referencePart(summarized)])),
    'fix this\n\nReferences:\nThe peak stress, 120 MPa, is above the 100 MPa this material yields at · /work/bracket.step#o1.f1,o1.f3');
});

test('a part picked in a model keeps its message: a label alone is not written', () => {
  const part = { resource: { kind: 'workspace-file', path: '/models/x.step' }, target: { kind: 'cad-selector', selectors: ['o1.2'] }, label: 'arm' };
  assert.equal(formatPromptMessage(createPromptContext([textPart('fix this'), referencePart(part)])), 'fix this\n\nReferences:\n/models/x.step#o1.2');
});

test('a summary must be text', () => {
  const bad = { resource: { kind: 'workspace-file', path: '/work/bracket.step' }, target: { kind: 'cad-selector', selectors: ['o1.f3'] }, summary: 4 };
  assert.throws(() => validatePromptContext(createPromptContext([referencePart(bad)])), /summary must be text/);
});
