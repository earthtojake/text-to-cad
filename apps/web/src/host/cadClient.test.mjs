import assert from 'node:assert/strict';
import test from 'node:test';
import { createWebCadClient } from './cadClient.js';

test('the web catalog poll asks nothing while the page is hidden, and reads the catalog again once it is shown', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] });
  const page = { visibilityState: 'visible' };
  let reads = 0;
  let revision = 'r1';
  const client = createWebCadClient({ document: page, fetch: async () => {
    reads += 1;
    return { ok: true, status: 200, json: async () => ({ revision, entries: [{ file: 'part.step', hash: revision }] }) };
  } });
  t.after(() => client.dispose());
  const settle = () => new Promise((resolve) => setImmediate(resolve));
  const tick = async (ms) => { for (let at = 0; at < ms; at += 2000) { t.mock.timers.tick(2000); await settle(); } };
  t.after(client.subscribe(() => {}));
  await settle();
  await tick(2000);
  assert.equal(reads, 2, 'a seen page reads its catalog every two seconds');
  page.visibilityState = 'hidden';
  revision = 'r2';
  await tick(10_000);
  assert.equal(reads, 2, 'a hidden page asks nothing');
  page.visibilityState = 'visible';
  await tick(2000);
  assert.equal(reads, 3);
  assert.equal(client.getSnapshot().entries[0].hash, 'r2');
});
