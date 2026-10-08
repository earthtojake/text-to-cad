// ONE-OFF, with ../../../scripts/migrate-neon-to-posthog.mjs: delete both once the migration has run.
import assert from 'node:assert/strict';
import test from 'node:test';

import { batchesOf, COLUMNS, eventsOf, goneInstalls, sql } from '../../../scripts/migrate-neon-to-posthog.mjs';
import { rowsOf } from './events.mjs';
import { EVENTS, propertiesOf } from './posthog.mjs';

const INSTALL = '6f1c2a51-7e3d-4f68-a1c4-2d5e8f903b77';
const SESSION = '0de4d024-c159-4f6d-b15a-cc4ef7a6856d';
const ARRIVED = '2026-10-03T12:00:00.123456+00:00'; // as Postgres' row_to_json writes a timestamptz
// A row of Neon's `events` table, as the export reads it.
const row = (id, fields) => ({
  id, received_at: ARRIVED, install_id: INSTALL, session_id: SESSION, tool: null, kind: null, calls: 1, errors: 0,
  version: '0.7.15', channel: 'claude-github', source: null, platform: 'darwin', arch: 'arm64', client: 'claude-ai',
  client_version: '1.0', presentation: 'inline', ...fields,
});

test('a stored batch becomes the events the receiver makes of the batch cadgen sent, at the time it arrived', () => {
  const stored = [row(1, { event: 'tool', tool: 'cad_show', calls: 3, errors: 1 }), row(2, { event: 'view', calls: 5 }),
    row(3, { event: 'file', kind: 'step' }), row(4, { event: 'file', kind: 'step' }), row(5, { event: 'file', kind: 'stl' })];
  const events = eventsOf(stored);
  const sent = {
    schema: 2, install: INSTALL, session: SESSION, version: '0.7.15', channel: 'claude-github', platform: 'darwin',
    arch: 'arm64', client: { name: 'claude-ai', version: '1.0' }, presentation: 'inline',
    events: [{ name: 'tool', tool: 'cad_show', calls: 3, errors: 1 }, { name: 'view', calls: 5 },
      { name: 'file', file: 'a'.repeat(16), kind: 'step' }, { name: 'file', file: 'b'.repeat(16), kind: 'step' },
      { name: 'file', file: 'c'.repeat(16), kind: 'stl' }],
  };
  assert.deepEqual(events.map(event => [event.event, event.properties]),
    rowsOf(sent).map(made => [EVENTS[made.event], { ...propertiesOf(made, null), migrated: 'neon' }]));
  assert.deepEqual(events.map(event => [event.event, event.properties.count ?? event.properties.calls]),
    [['tool_used', 3], ['view_used', 5], ['files_shown', 2], ['files_shown', 1]]);
  assert.ok(events.every(event => event.timestamp === '2026-10-03T12:00:00.123Z'));
  // No file's code, nor a country: the old rows kept none.
  assert.ok(events.every(event => !('file' in event.properties) && !('country' in event.properties)));
});

test('schema 1 named how it was installed, and the viewer said so by how it shows CAD', () => {
  const [event] = eventsOf([row(1, { event: 'view', version: '0.7.11', channel: 'unknown', source: 'store', presentation: 'browser' })]);
  assert.deepEqual([event.properties.source, event.properties.channel, event.properties.process], ['store', 'unknown', 'viewer']);
});

test('rows are put back into the batches they arrived in, and a rerun sends the same event ids', () => {
  const later = '2026-10-03T12:05:00+00:00';
  const stored = [row(1, { event: 'view' }), row(2, { event: 'tool', tool: 'cad_show' }), row(3, { event: 'view', received_at: later })];
  assert.deepEqual(batchesOf(stored).map(batch => batch.map(stored => stored.id)), [[1, 2], [3]]);
  const ids = batchesOf(stored).flatMap(eventsOf).map(event => event.uuid);
  assert.equal(new Set(ids).size, 3);
  assert.deepEqual(batchesOf(stored).flatMap(eventsOf).map(event => event.uuid), ids);
  assert.match(ids[0], /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/);
});

test('the installs that opted out between the copy and the switch are the ones gone from Neon', () => {
  const other = '9b0c2a51-7e3d-4f68-a1c4-2d5e8f903b77';
  const copied = [row(1, { event: 'view' }), row(2, { event: 'view', install_id: other })];
  assert.deepEqual(goneInstalls(copied, [other]), [INSTALL]);
  assert.deepEqual(goneInstalls(copied, [INSTALL, other]), []);
});

test("the export never reads a file's code", () => {
  assert.ok(!COLUMNS.includes('file'));
  assert.doesNotMatch(sql('events'), /\bfile\b/);
  assert.throws(() => sql('countries'), /no export named countries/);
});
