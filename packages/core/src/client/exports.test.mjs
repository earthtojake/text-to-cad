import assert from 'node:assert/strict';
import { test } from 'node:test';
import { createExportService, ExportRequestError } from '../../dist/client/exports.js';

test('export requests stay in the viewer session; the file is a plain session URL', async () => {
  const calls = [];
  const service = createExportService({ origin: 'https://example.test/s/session', fetch: async (url, init) => {
    calls.push({ url, ...init });
    return Response.json({ id: 'job', sequence: 7, state: 'ready' });
  } });
  const request = { requestId: 'stable-request', epoch: 'epoch', source: { doc: 'doc', revision: 'rev', part: null, pose: null }, format: 'step' };
  const abort = new AbortController();
  await service.create(request, abort.signal);
  await service.status('job', 7, abort.signal);
  await service.cancel('job');
  assert.equal(service.fileUrl('job/1'), 'https://example.test/s/session/__cad/exports/job%2F1/file');
  assert.equal(calls.length, 3, 'naming the file URL fetches nothing');
  assert.equal(calls[0].url, 'https://example.test/s/session/__cad/exports');
  assert.equal(calls[0].headers['x-cadgen-viewer'], '1');
  assert.deepEqual(JSON.parse(calls[0].body), request);
  assert.match(calls[1].url, /\/job\?after=7&wait=25$/);
  assert.equal(calls[1].signal, abort.signal);
  assert.match(calls[2].url, /\/job\/cancel$/);
});

test('an expired job reports its status for the toast, not a second generation', async () => {
  const service = createExportService({ fetch: async () => Response.json({ error: 'Expired' }, { status: 410 }) });
  await assert.rejects(service.status('old'), error => error instanceof ExportRequestError && error.status === 410 && error.message === 'Expired');
});
