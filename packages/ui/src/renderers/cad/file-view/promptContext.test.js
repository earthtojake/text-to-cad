import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createCadPromptContext } from './promptContext.js';
import { promptDeliveryMessage } from '../../kit/shell/promptContext.js';
test('capture context freezes revision and selected topology before encoding', async () => {
  const resource = { kind: 'workspace-file', workspaceId: 'one', path: 'parts/widget.step', revision: 'v1' };
  let resolve;
  const capture = new Promise(done => { resolve = done; });
  const context = createCadPromptContext({ resource, references: [{ selector: 'o1.f2,o1.e3', label: 'Selected edges' }], text: 'Round these', capture });
  resource.revision = 'v2';
  assert.equal(context.parts[0].reference.resource.revision, 'v1');
  assert.deepEqual(context.parts[0].reference.target, { kind: 'cad-selector', selectors: ['o1.f2', 'o1.e3'] });
  assert.deepEqual(context.parts[2].about, ['reference-0']);
  assert.equal(context.parts[2].name, 'widget-view.png');
  assert.throws(() => { context.parts[0].reference.resource.path = 'other.step'; }, TypeError);
  const blob = new Blob(['pixels'], { type: 'image/png' }); resolve(blob);
  assert.equal(await context.parts[2].content, blob);
});
test('whole-view captures retain provenance and delivery feedback reflects actual receipt', () => {
  const context = createCadPromptContext({ resource: { kind: 'workspace-file', workspaceId: 'one', path: 'part.stl' }, capture: new Blob(['pixels'], { type: 'image/png' }) });
  assert.deepEqual(context.parts[0].reference.target, { kind: 'whole-resource' });
  assert.deepEqual(context.parts[1].about, ['source']);
  assert.equal(promptDeliveryMessage({ status: 'added', partIds: ['source', 'capture'] }), 'Added to prompt');
  assert.equal(promptDeliveryMessage({ status: 'failed', message: 'Closed draft' }), 'Closed draft');
  assert.equal(promptDeliveryMessage({ status: 'partial', partIds: ['source'], message: 'Paste both representations' }), 'Paste both representations');
});
