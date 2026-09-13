import { encodeResourceUri } from '@emdash/core/primitives/path/api';
import type { ContentUnavailableCode, FileContentModel } from '@emdash/core/runtimes/files/api';
import { err, ok } from '@emdash/shared';
import type { Clock } from '@emdash/shared/scheduling';
import { waitFor } from '@emdash/shared/testing';
import { stableStringify } from '@emdash/shared/util';
import { defineContract } from '@emdash/wire/rpc';
import { cell, expose, snapshot, type Cell } from '@emdash/wire/state';
import { createTestWire } from '@emdash/wire/testing';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { filesWireContract, type FilesContentKey } from '@core/features/files/api';
import { hostFileRefFromNativePath, portablePath } from '@core/primitives/desktop-runtime/api';
import { HEAD_REF, type GitRef } from '@core/primitives/git/api';
import type { FacetDescriptor, FacetHandle, FacetHandleBinder } from './facet-handle';
import {
  BUFFER_AUTOSAVE_DEBOUNCE_MS,
  FIRST_LOAD_DEADLINE_MS,
  OPEN_FILE_LINGER_MS,
  OpenFileStore,
} from './open-file-store';

const wireClient = vi.hoisted(() => ({ current: undefined as unknown }));
const editorClient = vi.hoisted(() => ({ current: undefined as unknown }));

vi.mock('@core/features/files/api/browser/client', () => ({
  getFilesClient: async () => wireClient.current,
}));

vi.mock('@core/features/editor/api/browser/client', () => ({
  getEditorClient: async () => editorClient.current,
}));

const BUFFER = { kind: 'buffer' } as const;
const DISK = { kind: 'disk' } as const;

// ---------------------------------------------------------------------------
// Manual clock — drives the store's deadline / linger / autosave timers
// deterministically while the wire machinery keeps running on real microtasks.
// ---------------------------------------------------------------------------

type ManualClock = Clock & { advance(ms: number): void };

function createManualClock(): ManualClock {
  let now = 0;
  let seq = 0;
  const timers = new Map<number, { at: number; cb: () => void }>();
  const clock: ManualClock = {
    now: () => now,
    schedule(delayMs, callback) {
      seq += 1;
      const id = seq;
      timers.set(id, { at: now + Math.max(0, delayMs), cb: callback });
      return {
        get active() {
          return timers.has(id);
        },
        dispose() {
          timers.delete(id);
        },
      };
    },
    sleep(delayMs) {
      return new Promise((resolve) => {
        clock.schedule(delayMs, resolve);
      });
    },
    advance(ms) {
      const target = now + ms;
      for (;;) {
        const due = [...timers.entries()]
          .filter(([, timer]) => timer.at <= target)
          .sort((a, b) => a[1].at - b[1].at)[0];
        if (!due) break;
        timers.delete(due[0]);
        now = Math.max(now, due[1].at);
        due[1].cb();
      }
      now = target;
    },
  };
  return clock;
}

// ---------------------------------------------------------------------------
// Fake facet handles — the binder seam ticket 06 implements over Monaco.
// ---------------------------------------------------------------------------

class FakeFacetHandle implements FacetHandle {
  readonly descriptor: FacetDescriptor;
  disposed = false;
  private text: string;
  private readonly listeners = new Set<() => void>();

  constructor(descriptor: FacetDescriptor) {
    this.descriptor = descriptor;
    this.text = descriptor.initialText;
  }

  getText(): string {
    return this.text;
  }

  setText(text: string): void {
    if (text === this.text) return;
    this.text = text;
    for (const listener of [...this.listeners]) listener();
  }

  onDidChange(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  dispose(): void {
    this.disposed = true;
    this.listeners.clear();
  }
}

// ---------------------------------------------------------------------------
// Test harness: fakes the files domain over an in-process test wire (the
// files-store.test.ts pattern) and records provider lease acquire/release.
// ---------------------------------------------------------------------------

function textContent(content: string, etag: string): Extract<FileContentModel, { kind: 'text' }> {
  return {
    kind: 'text',
    path: portablePath('file.ts'),
    etag,
    byteSize: content.length,
    readonly: false,
    content,
    eol: 'lf',
  };
}

function unavailableContent(code: ContentUnavailableCode): FileContentModel {
  return { kind: 'unavailable', path: portablePath('file.ts'), code };
}

function setup() {
  const clock = createManualClock();
  const cells = new Map<string, Cell<FileContentModel | undefined>>();
  const resolves: FilesContentKey[] = [];
  const leases = { acquired: 0, released: 0 };
  let etagSeq = 0;

  const cellFor = (key: FilesContentKey): Cell<FileContentModel | undefined> => {
    const id = stableStringify(key);
    let existing = cells.get(id);
    if (!existing) {
      existing = cell<FileContentModel | undefined>(undefined);
      existing.set(undefined, { status: 'loading', notify: false });
      cells.set(id, existing);
    }
    return existing;
  };

  const provider = expose(
    filesWireContract.content,
    {
      content: (key) => {
        resolves.push(key);
        return cellFor(key);
      },
    },
    {
      lingerMs: 0,
      mutations: {
        write: async (context) => {
          const contentCell = cellFor(context.key);
          const current = snapshot(contentCell).value;
          const currentEtag = current?.kind === 'text' ? current.etag : undefined;
          const precondition = context.input.precondition;
          if (precondition.kind === 'etag' && precondition.etag !== currentEtag) {
            return err({
              type: 'etag-mismatch' as const,
              path: 'file.ts',
              expected: precondition.etag,
              actual: currentEtag ?? '',
            });
          }
          etagSeq += 1;
          const revision = contentCell.update(
            () => textContent(context.input.content, `write-${etagSeq}`),
            { mutationIds: [context.mutationId] }
          );
          await context.observed('content', revision);
          return ok(undefined);
        },
      },
    }
  );

  const countedProvider: typeof provider = {
    ...provider,
    acquireState(key, name) {
      const lease = provider.acquireState(key, name);
      leases.acquired += 1;
      return {
        ready: () => lease.ready(),
        release: async () => {
          leases.released += 1;
          await lease.release();
        },
      };
    },
  };

  const testContract = defineContract({ content: filesWireContract.content });
  const wire = createTestWire(testContract, { content: countedProvider });
  wireClient.current = wire.client;

  const saveBufferCalls: Array<{ uri: string; content: string }> = [];
  const clearBufferCalls: string[] = [];
  editorClient.current = {
    saveBuffer: async (input: { uri: string; content: string }) => {
      saveBufferCalls.push(input);
    },
    clearBuffer: async (input: { uri: string }) => {
      clearBufferCalls.push(input.uri);
    },
  };

  const createdHandles: FakeFacetHandle[] = [];
  const binder: FacetHandleBinder = {
    createHandle: (descriptor) => {
      const handle = new FakeFacetHandle(descriptor);
      createdHandles.push(handle);
      return handle;
    },
  };

  const store = new OpenFileStore({ clock });
  store.registerBinder(binder);

  const diskKey = (path: string): FilesContentKey => ({
    uri: encodeResourceUri(hostFileRefFromNativePath(path)),
    source: 'disk',
  });
  const gitKey = (path: string, ref: GitRef): FilesContentKey => ({
    uri: encodeResourceUri(hostFileRefFromNativePath(path)),
    source: { ref },
  });
  const publish = (key: FilesContentKey, value: FileContentModel) => {
    cellFor(key).set(value);
  };
  const diskContent = (key: FilesContentKey) => snapshot(cellFor(key)).value;

  return {
    store,
    clock,
    resolves,
    leases,
    createdHandles,
    saveBufferCalls,
    clearBufferCalls,
    diskKey,
    gitKey,
    publish,
    diskContent,
  };
}

type Harness = ReturnType<typeof setup>;

let harness: Harness | null = null;

function start(): Harness {
  harness = setup();
  return harness;
}

afterEach(async () => {
  await harness?.store.dispose();
  harness = null;
  wireClient.current = undefined;
  editorClient.current = undefined;
});

/** Acquire buffer+disk facets and drive the entry to ready with `content`. */
async function openReady(h: Harness, path: string, content: string, etag = 'e1') {
  const ref = hostFileRefFromNativePath(path);
  const bufferLease = h.store.acquire(ref, BUFFER);
  const diskLease = h.store.acquire(ref, DISK);
  h.publish(h.diskKey(path), textContent(content, etag));
  await waitFor(() => bufferLease.entry.status.kind === 'ready');
  await waitFor(
    () =>
      bufferLease.entry.handleFor(BUFFER) !== undefined &&
      bufferLease.entry.handleFor(DISK) !== undefined
  );
  return { ref, entry: bufferLease.entry, bufferLease, diskLease };
}

function bufferHandle(entry: { handleFor(facet: typeof BUFFER): FacetHandle | undefined }) {
  const handle = entry.handleFor(BUFFER);
  if (!handle) throw new Error('buffer handle missing');
  return handle as FakeFacetHandle;
}

describe('OpenFileStore', () => {
  describe('loading and facets', () => {
    it('loads disk content through the files domain and seeds the buffer from the disk facet', async () => {
      const h = start();
      const { entry } = await openReady(h, '/repo/src/index.ts', 'body');

      const buffer = bufferHandle(entry);
      const disk = entry.handleFor(DISK) as FakeFacetHandle;
      expect(buffer.getText()).toBe('body');
      expect(buffer.descriptor.readonly).toBe(false);
      expect(buffer.descriptor.uri).toBe(entry.uri);
      expect(disk.getText()).toBe('body');
      expect(disk.descriptor.readonly).toBe(true);

      expect(h.resolves).toEqual([h.diskKey('/repo/src/index.ts')]);
      expect(entry.dirty).toBe(false);
      expect(entry.conflicted).toBe(false);
      expect(entry.saving).toBe(false);
    });

    it('shares one entry and one in-flight load across spellings of the same ResourceKey', async () => {
      const h = start();
      const nfc = hostFileRefFromNativePath('/repo/caf\u00e9.ts');
      const nfd = hostFileRefFromNativePath('/repo/cafe\u0301.ts');

      const leaseA = h.store.acquire(nfc, BUFFER);
      const leaseB = h.store.acquire(nfd, BUFFER);
      expect(leaseB.entry).toBe(leaseA.entry);
      expect(h.store.peek(nfd)).toBe(leaseA.entry);

      h.publish(h.diskKey('/repo/caf\u00e9.ts'), textContent('shared', 'e1'));
      await waitFor(() => leaseA.entry.status.kind === 'ready');

      // One entry means one wire subscription under the first-seen spelling.
      expect(h.resolves).toHaveLength(1);
      expect(h.resolves[0]?.uri).toBe(encodeResourceUri(nfc));
    });

    it('holds git snapshot facets per ref alongside each other', async () => {
      const h = start();
      const path = '/repo/src/index.ts';
      const ref = hostFileRefFromNativePath(path);
      const commitRef: GitRef = { kind: 'commit', sha: 'abc123' };

      const headLease = h.store.acquire(ref, { kind: 'git', ref: HEAD_REF });
      const commitLease = h.store.acquire(ref, { kind: 'git', ref: commitRef });
      expect(commitLease.entry).toBe(headLease.entry);
      const entry = headLease.entry;

      h.publish(h.gitKey(path, HEAD_REF), { ...textContent('head text', 'git:1'), readonly: true });
      await waitFor(() => entry.gitStatus(HEAD_REF)?.kind === 'ready');
      expect(entry.gitStatus(commitRef)?.kind).toBe('loading');
      expect(entry.status.kind).toBe('loading');

      h.publish(h.gitKey(path, commitRef), {
        ...textContent('commit text', 'git:2'),
        readonly: true,
      });
      await waitFor(() => entry.gitStatus(commitRef)?.kind === 'ready');
      await waitFor(() => entry.status.kind === 'ready');

      await waitFor(
        () =>
          entry.handleFor({ kind: 'git', ref: HEAD_REF }) !== undefined &&
          entry.handleFor({ kind: 'git', ref: commitRef }) !== undefined
      );
      const headHandle = entry.handleFor({ kind: 'git', ref: HEAD_REF }) as FakeFacetHandle;
      const commitHandle = entry.handleFor({ kind: 'git', ref: commitRef }) as FakeFacetHandle;
      expect(headHandle.getText()).toBe('head text');
      expect(headHandle.descriptor.readonly).toBe(true);
      expect(commitHandle.getText()).toBe('commit text');
      expect(headHandle).not.toBe(commitHandle);

      const sources = h.resolves.map((key) => key.source);
      expect(sources).toContainEqual({ ref: HEAD_REF });
      expect(sources).toContainEqual({ ref: commitRef });
    });
  });

  describe('error classification', () => {
    it.each([['not-found' as const], ['no-permissions' as const], ['unavailable' as const]])(
      'classifies a first-load %s as error',
      async (code) => {
        const h = start();
        const ref = hostFileRefFromNativePath('/repo/missing.ts');
        const lease = h.store.acquire(ref, BUFFER);
        h.publish(h.diskKey('/repo/missing.ts'), unavailableContent(code));
        await waitFor(() => lease.entry.status.kind === 'error');
        expect(lease.entry.status).toEqual({ kind: 'error', code });
      }
    );

    it('classifies binary and too-large content as errors', async () => {
      const h = start();
      const ref = hostFileRefFromNativePath('/repo/blob.bin');
      const lease = h.store.acquire(ref, BUFFER);
      h.publish(h.diskKey('/repo/blob.bin'), {
        kind: 'binary',
        path: portablePath('blob.bin'),
        etag: 'e1',
        byteSize: 10,
        readonly: false,
      });
      await waitFor(() => lease.entry.status.kind === 'error');
      expect(lease.entry.status).toEqual({ kind: 'error', code: 'binary' });

      const ref2 = hostFileRefFromNativePath('/repo/huge.txt');
      const lease2 = h.store.acquire(ref2, BUFFER);
      h.publish(h.diskKey('/repo/huge.txt'), {
        kind: 'too-large',
        path: portablePath('huge.txt'),
        byteSize: 999,
        limit: 100,
      });
      await waitFor(() => lease2.entry.status.kind === 'error');
      expect(lease2.entry.status).toEqual({ kind: 'error', code: 'too-large' });
    });

    it('recovers a never-existed file to ready when it is created while interest is held', async () => {
      const h = start();
      const path = '/repo/docs/spec-to-be-written.md';
      const ref = hostFileRefFromNativePath(path);
      const bufferLease = h.store.acquire(ref, BUFFER);
      const diskLease = h.store.acquire(ref, DISK);

      h.publish(h.diskKey(path), unavailableContent('not-found'));
      await waitFor(() => bufferLease.entry.status.kind === 'error');
      expect(bufferLease.entry.status).toEqual({ kind: 'error', code: 'not-found' });

      // A chat link to a file the agent is about to write: when the file is
      // created, the live watch pushes content and the not-found placeholder
      // auto-recovers without any user action.
      h.publish(h.diskKey(path), textContent('# Spec', 'e1'));
      await waitFor(() => bufferLease.entry.status.kind === 'ready');
      await waitFor(() => bufferLease.entry.handleFor(BUFFER) !== undefined);
      expect(bufferHandle(bufferLease.entry).getText()).toBe('# Spec');

      bufferLease.release();
      diskLease.release();
    });

    it('hits the first-load deadline as error(unavailable) and recovers on late content', async () => {
      const h = start();
      const ref = hostFileRefFromNativePath('/repo/slow.ts');
      const lease = h.store.acquire(ref, BUFFER);
      expect(lease.entry.status.kind).toBe('loading');

      h.clock.advance(FIRST_LOAD_DEADLINE_MS - 1);
      expect(lease.entry.status.kind).toBe('loading');
      h.clock.advance(1);
      expect(lease.entry.status).toEqual({ kind: 'error', code: 'unavailable' });

      // The watch stays alive while interest is held: late content auto-recovers.
      h.publish(h.diskKey('/repo/slow.ts'), textContent('late', 'e1'));
      await waitFor(() => lease.entry.status.kind === 'ready');
    });

    it('re-attempts the load with a fresh deadline when an errored entry is re-acquired', async () => {
      const h = start();
      const ref = hostFileRefFromNativePath('/repo/slow.ts');
      const lease = h.store.acquire(ref, BUFFER);
      h.clock.advance(FIRST_LOAD_DEADLINE_MS);
      expect(lease.entry.status).toEqual({ kind: 'error', code: 'unavailable' });

      const retryLease = h.store.acquire(ref, BUFFER);
      expect(retryLease.entry).toBe(lease.entry);
      expect(retryLease.entry.status.kind).toBe('loading');

      h.clock.advance(FIRST_LOAD_DEADLINE_MS);
      expect(retryLease.entry.status).toEqual({ kind: 'error', code: 'unavailable' });

      h.publish(h.diskKey('/repo/slow.ts'), textContent('finally', 'e1'));
      await waitFor(() => retryLease.entry.status.kind === 'ready');
    });

    it('never caches failed loads: errored entries drop on last release and re-acquire re-attempts', async () => {
      const h = start();
      const ref = hostFileRefFromNativePath('/repo/broken.ts');
      const lease = h.store.acquire(ref, BUFFER);
      h.publish(h.diskKey('/repo/broken.ts'), unavailableContent('unavailable'));
      await waitFor(() => lease.entry.status.kind === 'error');

      // Error entries do not linger: the drop happens on release, not 15 s later.
      lease.release();
      expect(h.store.peek(ref)).toBeUndefined();
      await waitFor(() => h.leases.released === h.leases.acquired);

      const retry = h.store.acquire(ref, BUFFER);
      expect(retry.entry.status.kind).toBe('loading');
      await waitFor(() => h.resolves.length === 2);

      h.publish(h.diskKey('/repo/broken.ts'), textContent('fixed', 'e1'));
      await waitFor(() => retry.entry.status.kind === 'ready');
    });
  });

  describe('watcher-driven transitions', () => {
    it('orphans a ready entry on delete and auto-recovers when content reappears', async () => {
      const h = start();
      const path = '/repo/src/index.ts';
      const { entry } = await openReady(h, path, 'one');

      h.publish(h.diskKey(path), unavailableContent('not-found'));
      await waitFor(() => entry.status.kind === 'orphaned');
      // Buffer text survives orphaning.
      expect(bufferHandle(entry).getText()).toBe('one');

      h.publish(h.diskKey(path), textContent('two', 'e2'));
      await waitFor(() => entry.status.kind === 'ready');
      expect(bufferHandle(entry).getText()).toBe('two');
      expect(entry.dirty).toBe(false);
    });

    it('follows disk updates on a clean buffer and flags conflict on a dirty one', async () => {
      const h = start();
      const path = '/repo/src/index.ts';
      const { entry } = await openReady(h, path, 'one');

      h.publish(h.diskKey(path), textContent('two', 'e2'));
      await waitFor(() => bufferHandle(entry).getText() === 'two');
      expect(entry.dirty).toBe(false);
      expect(entry.conflicted).toBe(false);

      bufferHandle(entry).setText('two edited');
      await waitFor(() => entry.dirty);
      h.publish(h.diskKey(path), textContent('three', 'e3'));
      await waitFor(() => entry.conflicted);
      // The dirty buffer is preserved, not clobbered by the external change.
      expect(bufferHandle(entry).getText()).toBe('two edited');
      expect(entry.dirty).toBe(true);
    });
  });

  describe('save and conflict policy', () => {
    it('saves through the etag precondition and clears the crash-recovery buffer', async () => {
      const h = start();
      const path = '/repo/src/index.ts';
      const { entry } = await openReady(h, path, 'one');

      bufferHandle(entry).setText('one edited');
      await waitFor(() => entry.dirty);

      const result = await h.store.save(entry);
      expect(result).toEqual(ok(undefined));
      expect(entry.dirty).toBe(false);
      expect(entry.conflicted).toBe(false);
      expect(entry.saving).toBe(false);

      const disk = h.diskContent(h.diskKey(path));
      expect(disk?.kind === 'text' && disk.content).toBe('one edited');
      expect(h.clearBufferCalls).toEqual([entry.uri]);
    });

    it('flags conflict on a stale etag and resolves it by overwrite', async () => {
      const h = start();
      const path = '/repo/src/index.ts';
      const { entry } = await openReady(h, path, 'one');

      bufferHandle(entry).setText('mine');
      await waitFor(() => entry.dirty);
      h.publish(h.diskKey(path), textContent('theirs', 'e2'));
      await waitFor(() => entry.conflicted);

      const rejected = await h.store.save(entry);
      expect(rejected).toEqual(err({ type: 'conflict' }));
      expect(entry.conflicted).toBe(true);
      expect(entry.dirty).toBe(true);

      const overwritten = await h.store.save(entry, { overwrite: true });
      expect(overwritten).toEqual(ok(undefined));
      expect(entry.dirty).toBe(false);
      expect(entry.conflicted).toBe(false);
      const disk = h.diskContent(h.diskKey(path));
      expect(disk?.kind === 'text' && disk.content).toBe('mine');
    });

    it('resolves a conflict by reloading from disk and discarding the buffer', async () => {
      const h = start();
      const path = '/repo/src/index.ts';
      const { entry } = await openReady(h, path, 'one');

      bufferHandle(entry).setText('mine');
      await waitFor(() => entry.dirty);
      h.publish(h.diskKey(path), textContent('theirs', 'e2'));
      await waitFor(() => entry.conflicted);

      h.store.reloadFromDisk(entry);
      expect(bufferHandle(entry).getText()).toBe('theirs');
      expect(entry.dirty).toBe(false);
      expect(entry.conflicted).toBe(false);
      await waitFor(() => h.clearBufferCalls.includes(entry.uri));

      // A save right after the reload uses the fresh etag.
      bufferHandle(entry).setText('theirs edited');
      await waitFor(() => entry.dirty);
      expect(await h.store.save(entry)).toEqual(ok(undefined));
    });
  });

  describe('crash-recovery autosave', () => {
    it('persists dirty text after the debounce and clears it on save', async () => {
      const h = start();
      const path = '/repo/src/index.ts';
      const { entry } = await openReady(h, path, 'one');

      bufferHandle(entry).setText('one edited');
      await waitFor(() => entry.dirty);
      h.clock.advance(BUFFER_AUTOSAVE_DEBOUNCE_MS - 1);
      expect(h.saveBufferCalls).toHaveLength(0);
      h.clock.advance(1);
      await waitFor(() => h.saveBufferCalls.length === 1);
      expect(h.saveBufferCalls[0]).toEqual({ uri: entry.uri, content: 'one edited' });

      await h.store.save(entry);
      expect(h.clearBufferCalls).toContain(entry.uri);
    });

    it('does not persist a buffer that returned to clean before the debounce fires', async () => {
      const h = start();
      const path = '/repo/src/index.ts';
      const { entry } = await openReady(h, path, 'one');

      bufferHandle(entry).setText('one edited');
      await waitFor(() => entry.dirty);
      bufferHandle(entry).setText('one');
      await waitFor(() => !entry.dirty);

      h.clock.advance(BUFFER_AUTOSAVE_DEBOUNCE_MS);
      await new Promise((resolve) => setTimeout(resolve, 5));
      expect(h.saveBufferCalls).toHaveLength(0);
    });
  });

  describe('rename re-key', () => {
    it('re-keys an entry preserving buffer text and dirty state and transfers the recovery row', async () => {
      const h = start();
      const fromPath = '/repo/a.ts';
      const toPath = '/repo/b.ts';
      const from = hostFileRefFromNativePath(fromPath);
      const to = hostFileRefFromNativePath(toPath);
      const { entry } = await openReady(h, fromPath, 'hello');
      const oldUri = entry.uri;
      const oldBuffer = bufferHandle(entry);
      const oldDisk = entry.handleFor(DISK) as FakeFacetHandle;

      oldBuffer.setText('hello world');
      await waitFor(() => entry.dirty);

      await h.store.rekey(from, to);

      expect(h.store.peek(from)).toBeUndefined();
      expect(h.store.peek(to)).toBe(entry);
      expect(entry.uri).toBe(encodeResourceUri(to));
      expect(entry.dirty).toBe(true);
      expect(h.saveBufferCalls).toContainEqual({ uri: entry.uri, content: 'hello world' });
      expect(h.clearBufferCalls).toContain(oldUri);
      expect(oldBuffer.disposed).toBe(true);
      expect(oldDisk.disposed).toBe(true);

      h.publish(h.diskKey(toPath), textContent('hello', 'e9'));
      await waitFor(() => entry.status.kind === 'ready');
      await waitFor(() => entry.handleFor(BUFFER) !== undefined);

      const newBuffer = bufferHandle(entry);
      expect(newBuffer).not.toBe(oldBuffer);
      expect(newBuffer.descriptor.uri).toBe(entry.uri);
      expect(newBuffer.getText()).toBe('hello world');
      expect(entry.dirty).toBe(true);
      // The rename did not create a conflict: the disk did not change under the base.
      expect(entry.conflicted).toBe(false);
    });
  });

  describe('lifetimes', () => {
    it('releases facet handles and wire subscriptions together after the 15 s linger', async () => {
      const h = start();
      const { entry, bufferLease, diskLease } = await openReady(h, '/repo/src/index.ts', 'one');
      const buffer = bufferHandle(entry);
      const disk = entry.handleFor(DISK) as FakeFacetHandle;
      expect(h.leases.acquired).toBeGreaterThan(0);

      bufferLease.release();
      diskLease.release();
      h.clock.advance(OPEN_FILE_LINGER_MS - 1);
      expect(buffer.disposed).toBe(false);
      expect(h.store.peek(hostFileRefFromNativePath('/repo/src/index.ts'))).toBe(entry);

      h.clock.advance(1);
      expect(buffer.disposed).toBe(true);
      expect(disk.disposed).toBe(true);
      expect(h.store.peek(hostFileRefFromNativePath('/repo/src/index.ts'))).toBeUndefined();
      await waitFor(() => h.leases.released === h.leases.acquired);
    });

    it('re-acquiring within the linger window keeps the entry and subscription alive', async () => {
      const h = start();
      const ref = hostFileRefFromNativePath('/repo/src/index.ts');
      const { entry, bufferLease, diskLease } = await openReady(h, '/repo/src/index.ts', 'one');
      diskLease.release();
      bufferLease.release();

      h.clock.advance(OPEN_FILE_LINGER_MS - 1000);
      const again = h.store.acquire(ref, BUFFER);
      expect(again.entry).toBe(entry);

      h.clock.advance(OPEN_FILE_LINGER_MS * 2);
      expect(bufferHandle(entry).disposed).toBe(false);
      expect(h.store.peek(ref)).toBe(entry);
      // No re-resolve happened: the original subscription stayed live.
      expect(h.resolves).toHaveLength(1);
    });

    it('ref-counts acquirers: one release does not start the linger', async () => {
      const h = start();
      const ref = hostFileRefFromNativePath('/repo/src/index.ts');
      const leaseA = h.store.acquire(ref, BUFFER);
      const leaseB = h.store.acquire(ref, BUFFER);
      h.publish(h.diskKey('/repo/src/index.ts'), textContent('one', 'e1'));
      await waitFor(() => leaseA.entry.status.kind === 'ready');

      leaseA.release();
      leaseA.release(); // double release is a no-op
      h.clock.advance(OPEN_FILE_LINGER_MS * 2);
      expect(h.store.peek(ref)).toBe(leaseB.entry);

      leaseB.release();
      h.clock.advance(OPEN_FILE_LINGER_MS);
      expect(h.store.peek(ref)).toBeUndefined();
    });

    it('never evicts a dirty buffer; eviction resumes once the buffer is saved', async () => {
      const h = start();
      const ref = hostFileRefFromNativePath('/repo/src/index.ts');
      const { entry, bufferLease, diskLease } = await openReady(h, '/repo/src/index.ts', 'one');
      diskLease.release();

      bufferHandle(entry).setText('one edited');
      await waitFor(() => entry.dirty);
      bufferLease.release();

      h.clock.advance(OPEN_FILE_LINGER_MS * 4);
      expect(bufferHandle(entry).disposed).toBe(false);
      expect(h.store.peek(ref)).toBe(entry);

      const saved = await h.store.save(entry);
      expect(saved).toEqual(ok(undefined));
      h.clock.advance(OPEN_FILE_LINGER_MS);
      expect(h.store.peek(ref)).toBeUndefined();
      await waitFor(() => h.leases.released === h.leases.acquired);
    });
  });

  describe('dirty-buffer hydration (restore after restart)', () => {
    it('applies a persisted row to a clean open buffer and marks it dirty', async () => {
      const h = start();
      const path = '/repo/src/index.ts';
      const { ref, entry } = await openReady(h, path, 'disk text');

      h.store.hydrateBuffer(ref, 'recovered edits');

      expect(bufferHandle(entry).getText()).toBe('recovered edits');
      expect(entry.dirty).toBe(true);
      expect(entry.conflicted).toBe(false);
    });

    it('never clobbers edits the user made before hydration arrived', async () => {
      const h = start();
      const path = '/repo/src/index.ts';
      const { ref, entry } = await openReady(h, path, 'disk text');

      bufferHandle(entry).setText('typed after restart');
      await waitFor(() => entry.dirty);
      h.store.hydrateBuffer(ref, 'stale recovered edits');

      expect(bufferHandle(entry).getText()).toBe('typed after restart');
    });

    it('seeds a still-loading buffer so the row applies once content arrives', async () => {
      const h = start();
      const path = '/repo/src/slow.ts';
      const ref = hostFileRefFromNativePath(path);
      const lease = h.store.acquire(ref, BUFFER);
      expect(lease.entry.status.kind).toBe('loading');

      h.store.hydrateBuffer(ref, 'recovered edits');
      h.publish(h.diskKey(path), textContent('disk text', 'e1'));
      await waitFor(() => lease.entry.handleFor(BUFFER) !== undefined);

      expect(bufferHandle(lease.entry).getText()).toBe('recovered edits');
      expect(lease.entry.dirty).toBe(true);
    });

    it('leaves files that are not open alone', () => {
      const h = start();
      const ref = hostFileRefFromNativePath('/repo/not-open.ts');
      expect(() => h.store.hydrateBuffer(ref, 'row')).not.toThrow();
      expect(h.store.peek(ref)).toBeUndefined();
    });
  });

  describe('dirty-entry enumeration (quit guards)', () => {
    it('enumerates, saves, and discards dirty entries across files', async () => {
      const h = start();
      const a = await openReady(h, '/repo/a.ts', 'aaa');
      const b = await openReady(h, '/repo/b.ts', 'bbb');

      bufferHandle(a.entry).setText('aaa edited');
      bufferHandle(b.entry).setText('bbb edited');
      await waitFor(() => a.entry.dirty && b.entry.dirty);
      expect(h.store.dirtyEntries()).toHaveLength(2);

      await expect(h.store.saveAllDirty()).resolves.toBe(true);
      expect(h.store.dirtyEntries()).toHaveLength(0);

      bufferHandle(a.entry).setText('aaa again');
      await waitFor(() => a.entry.dirty);
      h.store.discardAllDirty();
      expect(bufferHandle(a.entry).getText()).toBe('aaa edited');
      expect(h.store.dirtyEntries()).toHaveLength(0);
    });
  });
});
