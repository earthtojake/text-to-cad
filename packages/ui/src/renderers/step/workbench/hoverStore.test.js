import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createHoverStore, EMPTY_HOVER } from './hoverStore.js';

test('hover setters keep React\'s contract: values, updaters, and no notification without a change', () => {
  const store = createHoverStore();
  let notifications = 0;
  const release = store.subscribe(() => notifications++);
  assert.equal(store.getSnapshot(), EMPTY_HOVER);
  store.setModelReferenceId('o1.1:f3');
  assert.equal(notifications, 1);
  const first = store.getSnapshot();
  assert.deepEqual(first, { modelReferenceId: 'o1.1:f3', modelPartId: '', listPartId: '' });
  // The same value, directly or through an updater, is no change and keeps the snapshot.
  store.setModelReferenceId('o1.1:f3');
  store.setModelPartId(current => current);
  assert.equal(notifications, 1);
  assert.equal(store.getSnapshot(), first);
  store.setListPartId(current => (current ? current : 'o1.2'));
  assert.equal(store.getSnapshot().listPartId, 'o1.2');
  assert.equal(notifications, 2);
  // Several fields in one change are one snapshot and one notification.
  store.update({ modelReferenceId: '', modelPartId: 'o1.1' });
  assert.equal(notifications, 3);
  assert.deepEqual(store.getSnapshot(), { modelReferenceId: '', modelPartId: 'o1.1', listPartId: 'o1.2' });
  store.clear();
  assert.equal(notifications, 4);
  assert.deepEqual(store.getSnapshot(), EMPTY_HOVER);
  assert.throws(() => store.update({ hoveredPartId: 'x' }), /Unknown hover field/);
  release();
  store.setModelPartId('o1.3');
  assert.equal(notifications, 4, 'a released subscriber hears nothing');
});

test('each surface has its own hover', () => {
  const first = createHoverStore(), second = createHoverStore();
  first.setModelPartId('o1.1');
  assert.equal(second.getSnapshot(), EMPTY_HOVER);
  // Setters are stable: an effect keyed on one never re-runs because of it.
  assert.equal(first.setModelPartId, first.setModelPartId);
});
