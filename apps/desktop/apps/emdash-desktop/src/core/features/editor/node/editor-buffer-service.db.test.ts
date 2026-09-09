import { mkdtemp, rm } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { hostRef, LOCAL_HOST_REF, type HostRef } from '@emdash/core/primitives/host/api';
import {
  encodeResourceUri,
  hostFileRef,
  parseAbsolute,
  type ResourceUri,
} from '@emdash/core/primitives/path/api';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import {
  createEditorBufferService,
  editorBufferDatabasePath,
  editorBufferSqliteStore,
  type EditorBufferService,
} from './editor-buffer-service';

const REMOTE_HOST = hostRef('remote', 'ssh-1');

function uriFor(path: string, host: HostRef = LOCAL_HOST_REF): ResourceUri {
  const parsed = parseAbsolute(path, {
    profile: { style: 'posix', unicodeNormalization: 'preserve' },
  });
  if (!parsed.success) throw new Error(parsed.error.message);
  return encodeResourceUri(hostFileRef(host, parsed.data));
}

describe('editorBufferDatabasePath', () => {
  it('keeps the buffer store beside and scoped to the app database', () => {
    expect(editorBufferDatabasePath('/tmp/emdash-scratch.db')).toBe(
      '/tmp/emdash-scratch-editor-buffers.db'
    );
    expect(editorBufferDatabasePath('/tmp/scratch')).toBe('/tmp/scratch-editor-buffers.db');
  });
});

describe('EditorBufferService', () => {
  let directory: string;
  let databasePath: string;
  let service: EditorBufferService;

  beforeEach(async () => {
    directory = await mkdtemp(join(tmpdir(), 'emdash-editor-buffers-'));
    databasePath = join(directory, 'editor-buffers.db');
    service = createEditorBufferService({ databasePath });
  });

  afterEach(async () => {
    service.dispose();
    await rm(directory, { recursive: true, force: true });
  });

  it('saves, upserts, and clears buffers keyed by ResourceUri', async () => {
    const uri = uriFor('/repo/src/index.ts');

    await service.saveBuffer(uri, 'first');
    await service.saveBuffer(uri, 'second');

    await expect(service.listBuffers()).resolves.toEqual([{ uri, content: 'second' }]);

    await service.clearBuffer(uri);
    await expect(service.listBuffers()).resolves.toEqual([]);
  });

  it('lists buffers under a root ResourceUri prefix only', async () => {
    const inside = uriFor('/repo/src/index.ts');
    const nested = uriFor('/repo/docs/notes/readme.md');
    const sibling = uriFor('/repo-other/src/index.ts');
    const outside = uriFor('/elsewhere/file.txt');
    await service.saveBuffer(inside, 'a');
    await service.saveBuffer(nested, 'b');
    await service.saveBuffer(sibling, 'c');
    await service.saveBuffer(outside, 'd');

    const buffers = await service.listBuffers(uriFor('/repo'));

    expect(buffers.map((buffer) => buffer.uri).sort()).toEqual([nested, inside].sort());
  });

  it('scopes root queries to the root host', async () => {
    const local = uriFor('/repo/file.ts');
    const remote = uriFor('/repo/file.ts', REMOTE_HOST);
    await service.saveBuffer(local, 'local');
    await service.saveBuffer(remote, 'remote');

    await expect(service.listBuffers(uriFor('/repo'))).resolves.toEqual([
      { uri: local, content: 'local' },
    ]);
    await expect(service.listBuffers(uriFor('/repo', REMOTE_HOST))).resolves.toEqual([
      { uri: remote, content: 'remote' },
    ]);
  });

  it('enumerates buffers outside any root via the unscoped listing', async () => {
    const external = uriFor('/tmp/scratch.md');
    const remote = uriFor('/home/user/notes.md', REMOTE_HOST);
    await service.saveBuffer(external, 'scratch');
    await service.saveBuffer(remote, 'notes');

    const buffers = await service.listBuffers();

    expect(buffers.map((buffer) => buffer.uri).sort()).toEqual([external, remote].sort());
  });

  it('treats percent-encoded characters literally in prefix matching', async () => {
    const spaced = uriFor('/repo dir/my file.ts');
    const decoy = uriFor('/repoXdirY/my file.ts');
    await service.saveBuffer(spaced, 'spaced');
    await service.saveBuffer(decoy, 'decoy');

    await expect(service.listBuffers(uriFor('/repo dir'))).resolves.toEqual([
      { uri: spaced, content: 'spaced' },
    ]);
  });

  it('prunes stale buffers', async () => {
    const fresh = uriFor('/repo/fresh.ts');
    const stale = uriFor('/repo/stale.ts');
    await service.saveBuffer(fresh, 'fresh');
    await service.saveBuffer(stale, 'stale');
    service.dispose();

    const tamper = editorBufferSqliteStore.open(databasePath);
    tamper.connection.run(`UPDATE editor_buffers SET updated_at = 0 WHERE uri = ?`, [
      stale as string,
    ]);
    tamper.close();
    service = createEditorBufferService({ databasePath });

    await service.pruneStale();

    await expect(service.listBuffers()).resolves.toEqual([{ uri: fresh, content: 'fresh' }]);
  });

  it('drops and recreates the store on a user_version mismatch', async () => {
    await service.saveBuffer(uriFor('/repo/file.ts'), 'dirty');
    service.dispose();

    const tamper = editorBufferSqliteStore.open(databasePath);
    tamper.connection.exec('PRAGMA user_version = 1');
    tamper.close();
    service = createEditorBufferService({ databasePath });

    await expect(service.listBuffers()).resolves.toEqual([]);
    const uri = uriFor('/repo/file.ts');
    await service.saveBuffer(uri, 'fresh start');
    await expect(service.listBuffers()).resolves.toEqual([{ uri, content: 'fresh start' }]);
  });
});
