import assert from 'node:assert/strict';
import { test } from 'node:test';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { verifyServedViewerClient } from './fingerprint.mjs';

test('served client proof rejects another checkout even when local fingerprints are unchanged', async () => {
  const dist = fs.mkdtempSync(path.join(os.tmpdir(), 'viewer-client-proof-'));
  try {
    fs.mkdirSync(path.join(dist, 'assets'));
    fs.writeFileSync(path.join(dist, 'index.html'), '<script src="/assets/index-x.js"></script>');
    fs.writeFileSync(path.join(dist, 'assets/index-x.js'), 'current client');
    const read = async url => new Response(fs.readFileSync(path.join(dist, url.pathname === '/' ? 'index.html' : url.pathname)));
    const proof = await verifyServedViewerClient('http://127.0.0.1:3271', { dist, fetchImpl: read });
    assert.equal(proof.matches, true);
    assert.equal(proof.files.length, 2);
    await assert.rejects(verifyServedViewerClient('http://127.0.0.1:3271', {
      dist, fetchImpl: async () => new Response('another checkout'),
    }), /Served client differs/);
  } finally { fs.rmSync(dist, { recursive: true, force: true }); }
});
