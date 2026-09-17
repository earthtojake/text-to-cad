import test from 'node:test';
import assert from 'node:assert/strict';
import { createPromptContext, referencePart, textPart, validatePromptContext, formatPromptContextText, formatPromptReference } from './index.js';

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
