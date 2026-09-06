import { observable, runInAction } from 'mobx';
import { describe, expect, it, vi } from 'vitest';
import type {
  ContentStatus,
  OpenFileEntry,
  OpenFileLease,
  OpenFileStore,
} from '@core/features/editor/api/browser/open-file-store/open-file-store';
import { FileTabResource } from '@core/features/editor/api/browser/task-editor/stores/file-tab-resource';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import type { TabHandle } from '@core/primitives/workbench-shell/browser/tabs/core/tab-provider';

// ---------------------------------------------------------------------------
// Fake OpenFileStore seam — one observable entry, recorded acquire/release.
// ---------------------------------------------------------------------------

class FakeHandle {
  private text = '';
  private readonly listeners = new Set<() => void>();

  getText(): string {
    return this.text;
  }

  setText(text: string): void {
    this.text = text;
    for (const listener of [...this.listeners]) listener();
  }

  onDidChange(listener: () => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

function createFakeStore() {
  const handles = observable.map<string, FakeHandle>();
  const state = observable.object({
    status: { kind: 'loading' } as ContentStatus,
    dirty: false,
  });
  const entry = {
    key: 'key' as never,
    uri: 'uri' as never,
    get status() {
      return state.status;
    },
    get dirty() {
      return state.dirty;
    },
    conflicted: false,
    saving: false,
    handleFor: (facet: { kind: string }) => handles.get(facet.kind),
    gitStatus: () => undefined,
  } as unknown as OpenFileEntry;

  const acquired: Array<{ facet: string; released: boolean }> = [];
  const store: Pick<OpenFileStore, 'acquire'> = {
    acquire: (_ref, facet) => {
      const record = { facet: facet.kind, released: false };
      acquired.push(record);
      return {
        entry,
        release: () => {
          record.released = true;
        },
      } as OpenFileLease;
    },
  };

  return {
    store,
    entry,
    acquired,
    setStatus: (status: ContentStatus) =>
      runInAction(() => {
        state.status = status;
      }),
    setDirty: (dirty: boolean) =>
      runInAction(() => {
        state.dirty = dirty;
      }),
    provideBufferHandle: () => {
      const handle = new FakeHandle();
      runInAction(() => handles.set('buffer', handle));
      return handle;
    },
  };
}

const REF = hostFileRefFromNativePath('/repo/src/index.ts');

describe('FileTabResource content leases', () => {
  it('acquires buffer+disk facets on construction and releases both on dispose', () => {
    const fake = createFakeStore();
    const resource = new FileTabResource(
      { path: '/repo/src/index.ts' },
      {
        ref: REF,
        store: fake.store,
      }
    );

    expect(fake.acquired.map((r) => r.facet).sort()).toEqual(['buffer', 'disk']);
    expect(resource.contentStatus).toEqual({ kind: 'loading' });

    resource.dispose();
    expect(fake.acquired.every((r) => r.released)).toBe(true);
  });

  it('renders content status and dirty state straight from the store entry', () => {
    const fake = createFakeStore();
    const resource = new FileTabResource(
      { path: '/repo/src/index.ts' },
      {
        ref: REF,
        store: fake.store,
      }
    );

    fake.setStatus({ kind: 'ready' });
    expect(resource.contentStatus).toEqual({ kind: 'ready' });
    fake.setDirty(true);
    expect(resource.isDirty).toBe(true);

    fake.setStatus({ kind: 'orphaned' });
    expect(resource.contentStatus).toEqual({ kind: 'orphaned' });
    fake.setStatus({ kind: 'error', code: 'not-found' });
    expect(resource.contentStatus).toEqual({ kind: 'error', code: 'not-found' });

    resource.dispose();
  });

  it('bumps bufferVersion when the buffer handle appears and on every change', () => {
    const fake = createFakeStore();
    const resource = new FileTabResource(
      { path: '/repo/src/index.ts' },
      {
        ref: REF,
        store: fake.store,
      }
    );
    expect(resource.bufferVersion).toBe(0);

    const handle = fake.provideBufferHandle();
    expect(resource.bufferVersion).toBe(1);

    handle.setText('edited');
    expect(resource.bufferVersion).toBe(2);
    expect(resource.bufferText()).toBe('edited');

    resource.dispose();
    handle.setText('after dispose');
    expect(resource.bufferVersion).toBe(2);
  });

  it('retryLoad overlaps fresh leases with the old ones before releasing', () => {
    const fake = createFakeStore();
    const resource = new FileTabResource(
      { path: '/repo/src/index.ts' },
      {
        ref: REF,
        store: fake.store,
      }
    );

    resource.retryLoad();

    expect(fake.acquired).toHaveLength(4);
    expect(fake.acquired.slice(0, 2).every((r) => r.released)).toBe(true);
    expect(fake.acquired.slice(2).every((r) => !r.released)).toBe(true);

    resource.dispose();
    expect(fake.acquired.every((r) => r.released)).toBe(true);
  });

  it('treats files outside any workspace root as ordinary store-backed tabs', () => {
    const fake = createFakeStore();
    const outside = new FileTabResource(
      { path: '/somewhere/README.md' },
      {
        ref: hostFileRefFromNativePath('/somewhere/README.md'),
        store: fake.store,
        inWorkspace: false,
        displayPath: '/somewhere/README.md',
      }
    );

    expect(outside.usesOpenFileStore).toBe(true);
    expect(fake.acquired.map((r) => r.facet).sort()).toEqual(['buffer', 'disk']);
    expect(outside.inWorkspace).toBe(false);
    expect(outside.contentStatus).toEqual({ kind: 'loading' });

    outside.dispose();
  });

  it('does not touch the store for unresolvable refs', () => {
    const fake = createFakeStore();
    const unresolvable = new FileTabResource(
      { path: 'src/index.ts' },
      {
        ref: null,
        store: fake.store,
      }
    );
    expect(fake.acquired).toHaveLength(0);
    expect(unresolvable.contentStatus).toEqual({ kind: 'error', code: 'unavailable' });
  });

  it('pins a preview tab once its buffer turns dirty', () => {
    const fake = createFakeStore();
    const pin = vi.fn();
    const resource = new FileTabResource(
      { path: '/repo/src/index.ts' },
      {
        ref: REF,
        store: fake.store,
        handle: { pin } as unknown as TabHandle,
      }
    );

    expect(pin).not.toHaveBeenCalled();
    fake.setDirty(true);
    expect(pin).toHaveBeenCalledTimes(1);

    resource.dispose();
  });
});

describe('FileTabResource selections', () => {
  it('switches previewable files to source and exposes a one-shot selection request', () => {
    const resource = new FileTabResource({ path: 'README.md' });
    expect(resource.viewMode).toBe('preview');

    resource.requestSelection({ lineNumber: 8, startColumn: 4, endColumn: 10 });

    expect(resource.viewMode).toBe('source');
    expect(resource.selectionRequest).toEqual({
      id: 1,
      selection: { lineNumber: 8, startColumn: 4, endColumn: 10 },
    });

    resource.consumeSelectionRequest(2);
    expect(resource.selectionRequest?.id).toBe(1);
    resource.consumeSelectionRequest(1);
    expect(resource.selectionRequest).toBeNull();
  });
});
