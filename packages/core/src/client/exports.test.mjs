import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createExportService, ExportRequestError } from '../../dist/client/exports.js';

test('export requests stay in the viewer session; the file is a plain session URL', async () => {
  const calls = [];
  const service = createExportService({ origin: 'https://example.test/s/session', fetch: async (url, init) => {
    calls.push({ url, ...init });
    return Response.json({ id: 'job', sequence: 7, state: 'ready', epoch: 'session-epoch' });
  } });
  const abort = new AbortController();
  // The session's epoch is one plain read of the exports route, the one thing a new request asks first.
  assert.equal(await service.epoch(abort.signal), 'session-epoch');
  const request = { requestId: 'stable-request', epoch: 'session-epoch', source: { doc: 'doc', revision: 'rev' }, format: 'step' };
  await service.create(request, abort.signal);
  await service.status('job', 7, abort.signal);
  assert.equal(service.fileUrl('job/1'), 'https://example.test/s/session/__cad/exports/job%2F1/file');
  assert.equal(calls.length, 3, 'naming the file URL fetches nothing');
  assert.deepEqual([calls[0].url, calls[0].method, calls[0].body, calls[0].signal], ['https://example.test/s/session/__cad/exports', undefined, undefined, abort.signal]);
  assert.equal(calls[1].url, 'https://example.test/s/session/__cad/exports');
  assert.equal(calls[1].headers['x-cadgen-viewer'], '1');
  assert.deepEqual(JSON.parse(calls[1].body), request);
  assert.match(calls[2].url, /\/job\?after=7&wait=25$/);
  assert.equal(calls[2].signal, abort.signal);
});

test('an expired job reports its status for the toast, not a second generation', async () => {
  const service = createExportService({ fetch: async () => Response.json({ error: 'Expired' }, { status: 410 }) });
  await assert.rejects(service.status('old'), error => error instanceof ExportRequestError && error.status === 410 && error.message === 'Expired');
});
