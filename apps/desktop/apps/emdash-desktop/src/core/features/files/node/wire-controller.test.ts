import { hostRef, LOCAL_HOST_REF } from '@emdash/core/primitives/host/api';
import {
  encodeResourceUri,
  hostFileRef,
  parseAbsolute,
  type HostAbsolutePath,
} from '@emdash/core/primitives/path/api';
import type { RuntimeResolveError } from '@emdash/core/services/runtime-broker/api';
import { err, ok } from '@emdash/shared';
import type { LiveSource } from '@emdash/wire/rpc';
import { encodeTopic, isDownloadFileOpenResult } from '@emdash/wire/rpc';
import { describe, expect, it, vi } from 'vitest';
import { filesWireContract } from '../api';
import { createFilesWireController } from './wire-controller';

const remoteHost = hostRef('remote', 'ssh-2');

describe('createFilesWireController', () => {
  it('decodes the URI and routes each fs procedure to the host it names', async () => {
    const exists = vi.fn(async () => ok({ exists: true }));
    const client = vi.fn(async () => ok({ files: { fs: { exists } } }));
    const controller = createFilesWireController({ runtimes: { client } as never });

    await expect(
      controller.call('fs.exists', { uri: uriFor(LOCAL_HOST_REF, '/repo/a.txt') })
    ).resolves.toEqual(ok({ exists: true }));
    expect(client).toHaveBeenLastCalledWith(LOCAL_HOST_REF);
    expect(exists).toHaveBeenLastCalledWith({ path: absolute('/repo/a.txt') }, {});

    await expect(
      controller.call('fs.exists', { uri: uriFor(remoteHost, '/home/dev/b.txt') })
    ).resolves.toEqual(ok({ exists: true }));
    expect(client).toHaveBeenLastCalledWith(remoteHost);
    expect(exists).toHaveBeenLastCalledWith({ path: absolute('/home/dev/b.txt') }, {});
  });

  it('resolves the decoded host for each attached content state', async () => {
    const source = liveSource({ kind: 'text', content: 'test' });
    const state = vi.fn(() => ({ asLiveSource: () => source }));
    const client = vi.fn(async () => ok({ files: { content: { state } } }));
    const controller = createFilesWireController({ runtimes: { client } as never });
    const key = { uri: uriFor(remoteHost, '/home/dev/README.md'), source: 'disk' as const };
    const topic = encodeTopic(filesWireContract.content.states.content.id, key);

    const lease = controller.acquireLive(topic);
    await expect(lease?.ready()).resolves.toBe(source);
    expect(client).toHaveBeenCalledWith(remoteHost);
    expect(state).toHaveBeenCalledWith({ path: absolute('/home/dev/README.md') }, 'content');

    await lease?.release();
  });

  it('resolves the decoded root host for the tree model', async () => {
    const source = liveSource({ entries: {} });
    const state = vi.fn(() => ({ asLiveSource: () => source }));
    const client = vi.fn(async () => ok({ files: { tree: { model: { state } } } }));
    const controller = createFilesWireController({ runtimes: { client } as never });
    const key = {
      root: uriFor(remoteHost, '/home/dev/project'),
      sessionId: 'session-1',
      exclusions: ['node_modules'],
    };
    const topic = encodeTopic(filesWireContract.tree.model.states.tree.id, key);

    const lease = controller.acquireLive(topic);
    await expect(lease?.ready()).resolves.toBe(source);
    expect(client).toHaveBeenCalledWith(remoteHost);
    expect(state).toHaveBeenCalledWith(
      {
        root: absolute('/home/dev/project'),
        sessionId: 'session-1',
        exclusions: ['node_modules'],
      },
      'tree'
    );

    await lease?.release();
  });

  it('forwards fs writes with decoded absolute targets', async () => {
    const createDirectory = vi.fn(async () => ok(undefined));
    const deleteEntry = vi.fn(async () => ok(undefined));
    const rename = vi.fn(async () => ok(undefined));
    const client = vi.fn(async () =>
      ok({ files: { fs: { createDirectory, delete: deleteEntry, rename } } })
    );
    const controller = createFilesWireController({ runtimes: { client } as never });

    await expect(
      controller.call('fs.createDirectory', {
        uri: uriFor(LOCAL_HOST_REF, '/repo/new-dir'),
      })
    ).resolves.toEqual(ok(undefined));
    expect(createDirectory).toHaveBeenCalledWith({ path: absolute('/repo/new-dir') }, {});

    await expect(
      controller.call('fs.delete', {
        uri: uriFor(LOCAL_HOST_REF, '/repo/new-dir'),
        recursive: true,
      })
    ).resolves.toEqual(ok(undefined));
    expect(deleteEntry).toHaveBeenCalledWith(
      { path: absolute('/repo/new-dir'), recursive: true },
      {}
    );

    await expect(
      controller.call('fs.rename', {
        from: uriFor(LOCAL_HOST_REF, '/repo/a.txt'),
        to: uriFor(LOCAL_HOST_REF, '/repo/b.txt'),
      })
    ).resolves.toEqual(ok(undefined));
    expect(rename).toHaveBeenCalledWith(
      { from: absolute('/repo/a.txt'), to: absolute('/repo/b.txt') },
      {}
    );
  });

  it('passes the downloaded byte stream through', async () => {
    const chunks = async function* () {
      yield new Uint8Array([1, 2, 3]);
    };
    const readBytes = vi.fn(async () =>
      ok({
        meta: {
          name: 'image.png',
          mimeType: 'image/png',
          truncated: false,
          totalSize: 3,
          etag: 'etag-1',
        },
        chunks,
      })
    );
    const controller = createFilesWireController({
      runtimes: { client: async () => ok({ files: { fs: { readBytes } } }) } as never,
    });

    const result = await controller.call('fs.readBytes', {
      uri: uriFor(LOCAL_HOST_REF, '/repo/image.png'),
    });

    expect(isDownloadFileOpenResult(result)).toBe(true);
    if (!isDownloadFileOpenResult(result)) throw new Error('Expected a download source');
    for await (const _chunk of result.data.source as AsyncIterable<Uint8Array>) {
      // Consume the source.
    }
  });

  it('rejects content writes for git-ref sources without resolving any runtime', async () => {
    const client = vi.fn();
    const controller = createFilesWireController({ runtimes: { client } as never });

    await expect(
      controller.call('content.write', {
        key: { uri: uriFor(LOCAL_HOST_REF, '/repo/a.txt'), source: { ref: { kind: 'head' } } },
        input: { content: 'must not land', precondition: { kind: 'overwrite' } },
        mutationId: 'mutation-git-1',
      })
    ).resolves.toMatchObject({
      success: false,
      error: { type: 'permission-denied', path: '/repo/a.txt' },
    });
    expect(client).not.toHaveBeenCalled();
  });

  it('returns RuntimeResolveError from fallible procedures and mutations', async () => {
    const resolveError: RuntimeResolveError = {
      type: 'host-unavailable',
      host: LOCAL_HOST_REF,
      reason: 'runtime-unavailable',
      message: 'Runtime unavailable',
    };
    const controller = createFilesWireController({
      runtimes: { client: async () => err(resolveError) } as never,
    });
    const uri = uriFor(LOCAL_HOST_REF, '/repo/README.md');

    await expect(controller.call('fs.exists', { uri })).resolves.toEqual(err(resolveError));
    await expect(controller.call('fs.readBytes', { uri })).resolves.toEqual(err(resolveError));
    await expect(controller.call('fs.delete', { uri })).resolves.toEqual(err(resolveError));
    await expect(
      controller.call('fs.rename', { from: uri, to: uriFor(LOCAL_HOST_REF, '/repo/x.md') })
    ).resolves.toEqual(err(resolveError));
    await expect(
      controller.call('content.write', {
        key: { uri, source: 'disk' },
        input: { content: 'updated', precondition: { kind: 'overwrite' } },
        mutationId: 'mutation-1',
      })
    ).resolves.toEqual(err(resolveError));
  });
});

function absolute(path: string): HostAbsolutePath {
  const parsed = parseAbsolute(path, { profile: { style: 'posix' } });
  if (!parsed.success) throw new Error(parsed.error.message);
  return parsed.data;
}

function uriFor(host: Parameters<typeof hostFileRef>[0], path: string) {
  return encodeResourceUri(hostFileRef(host, absolute(path)));
}

function liveSource(data: unknown): LiveSource {
  return {
    snapshot: async () => ({ generation: 1, sequence: 0, timestamp: 0, data }),
    subscribe: () => () => {},
  };
}
