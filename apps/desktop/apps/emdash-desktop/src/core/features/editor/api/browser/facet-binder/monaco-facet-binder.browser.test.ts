import { hostRef } from '@emdash/core/primitives/host/api';
import { encodeResourceUri, hostFileRef, type HostFileRef } from '@emdash/core/primitives/path/api';
import type { FileContentModel } from '@emdash/core/runtimes/files/api';
import { ok } from '@emdash/shared';
import { waitFor } from '@emdash/shared/testing';
import { stableStringify } from '@emdash/shared/util';
import { defineContract } from '@emdash/wire/rpc';
import { cell, expose, type Cell } from '@emdash/wire/state';
import { createTestWire } from '@emdash/wire/testing';
import * as monaco from 'monaco-editor';
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type {
  Facet,
  FacetDescriptor,
} from '@core/features/editor/api/browser/open-file-store/facet-handle';
import { OpenFileStore } from '@core/features/editor/api/browser/open-file-store/open-file-store';
import { filesWireContract, type FilesContentKey } from '@core/features/files/api';
import { portablePath } from '@core/primitives/desktop-runtime/api';
import { encodeFacetUri } from './facet-uri';
import { MonacoFacetBinder } from './monaco-facet-binder';

const wireClient = vi.hoisted(() => ({ current: undefined as unknown }));

vi.mock('@core/features/files/api/browser/client', () => ({
  getFilesClient: async () => wireClient.current,
}));

vi.mock('@core/features/editor/api/browser/client', () => ({
  getEditorClient: async () => ({
    saveBuffer: async () => undefined,
    clearBuffer: async () => undefined,
  }),
}));

self.MonacoEnvironment = {
  getWorker: () => new editorWorker(),
};

// Disposing editors/models with in-flight worker requests makes Monaco
// internals reject pending promises with its Canceled error; those are
// expected teardown noise, not test failures.
addEventListener('unhandledrejection', (event) => {
  const reason: unknown = event.reason;
  if (reason instanceof Error && reason.name === 'Canceled') event.preventDefault();
});

const BUFFER: Facet = { kind: 'buffer' };
const DISK: Facet = { kind: 'disk' };

function fileRef(...segments: string[]): HostFileRef {
  return hostFileRef(hostRef('local', 'local'), { root: { kind: 'posix' }, segments });
}

function descriptor(ref: HostFileRef, facet: Facet, initialText: string): FacetDescriptor {
  return { uri: encodeResourceUri(ref), facet, initialText, readonly: facet.kind !== 'buffer' };
}

// ---------------------------------------------------------------------------
// Cleanup tracking — models, editors, and containers per test
// ---------------------------------------------------------------------------

const cleanups: Array<() => void | Promise<void>> = [];

afterEach(async () => {
  for (const cleanup of cleanups.splice(0).reverse()) await cleanup();
});

function newBinder(loader: () => Promise<typeof monaco> = async () => monaco): MonacoFacetBinder {
  return new MonacoFacetBinder(loader);
}

async function createHandle(binder: MonacoFacetBinder, d: FacetDescriptor) {
  const handle = await binder.createHandle(d);
  cleanups.push(() => handle.dispose());
  return handle;
}

function createEditorContainer(): HTMLElement {
  const container = document.createElement('div');
  container.style.width = '600px';
  container.style.height = '400px';
  document.body.appendChild(container);
  cleanups.push(() => container.remove());
  return container;
}

function createEditor(): monaco.editor.IStandaloneCodeEditor {
  const editor = monaco.editor.create(createEditorContainer(), { model: null });
  cleanups.push(() => editor.dispose());
  return editor;
}

function createDiffEditor(): monaco.editor.IStandaloneDiffEditor {
  const editor = monaco.editor.createDiffEditor(createEditorContainer(), {});
  cleanups.push(() => {
    editor.setModel(null);
    editor.dispose();
  });
  return editor;
}

// ---------------------------------------------------------------------------
// Codec ⇄ Monaco Uri canonical stability
// ---------------------------------------------------------------------------

describe('facet URIs under real Monaco', () => {
  it('round-trips codec output through monaco.Uri.parse/toString byte-for-byte', () => {
    const refs: Array<[HostFileRef, Facet]> = [
      [fileRef('repo', 'src', 'index.ts'), BUFFER],
      [fileRef('dir with spaces', 'caf\u00e9 100%.ts'), DISK],
      [fileRef("it's (tricky)*!.md"), BUFFER],
      [
        hostFileRef(hostRef('remote', 'ssh:user@host/conn'), {
          root: { kind: 'posix' },
          segments: ['home', 'file.ts'],
        }),
        DISK,
      ],
      [fileRef('repo', 'file.ts'), { kind: 'git', ref: { kind: 'head' } }],
      [
        fileRef('repo', 'file.ts'),
        {
          kind: 'git',
          ref: {
            kind: 'branch',
            branch: {
              type: 'remote',
              branch: 'release/2024.1/hot fix',
              remote: { name: 'my/remote', url: '' },
            },
          },
        },
      ],
    ];
    for (const [ref, facet] of refs) {
      const uri = encodeFacetUri(ref, facet);
      expect(monaco.Uri.parse(uri).toString(), uri).toBe(uri);
    }
  });
});

// ---------------------------------------------------------------------------
// Handle behavior over real ITextModels
// ---------------------------------------------------------------------------

describe('MonacoFacetBinder handles', () => {
  it('creates the model at the codec-derived URI with initial text and inferred language', async () => {
    const binder = newBinder();
    const ref = fileRef('repo', 'src', 'main.ts');
    await createHandle(binder, descriptor(ref, BUFFER, 'const x = 1;\n'));

    const uri = encodeFacetUri(ref, BUFFER);
    const model = monaco.editor.getModel(monaco.Uri.parse(uri));
    expect(model).not.toBeNull();
    expect(model?.getValue()).toBe('const x = 1;\n');
    expect(model?.getLanguageId()).toBe('typescript');
    expect(binder.modelFor(uri)).toBe(model);
  });

  it('delivers change events synchronously for setText and user edits', async () => {
    const binder = newBinder();
    const ref = fileRef('repo', 'sync.txt');
    const handle = await createHandle(binder, descriptor(ref, BUFFER, 'one'));

    let notified = 0;
    handle.onDidChange(() => {
      notified += 1;
    });

    handle.setText('two');
    expect(notified).toBe(1);
    expect(handle.getText()).toBe('two');

    const model = binder.modelFor(encodeFacetUri(ref, BUFFER));
    if (!model) throw new Error('model missing');
    model.applyEdits([{ range: model.getFullModelRange().collapseToEnd(), text: '!' }]);
    expect(notified).toBe(2);
    expect(handle.getText()).toBe('two!');
  });

  it('preserves undo stack and cursor across external setText', async () => {
    const binder = newBinder();
    const ref = fileRef('repo', 'undo.txt');
    const handle = await createHandle(binder, descriptor(ref, BUFFER, 'alpha\nbravo\ncharlie\n'));
    const uri = encodeFacetUri(ref, BUFFER);
    const model = binder.modelFor(uri);
    if (!model) throw new Error('model missing');

    const editor = createEditor();
    binder.attach(editor, uri);
    editor.setPosition({ lineNumber: 3, column: 1 });
    editor.trigger('keyboard', 'type', { text: 'x' });
    expect(model.getValue()).toBe('alpha\nbravo\nxcharlie\n');
    expect(editor.getPosition()).toMatchObject({ lineNumber: 3, column: 2 });

    // External content update touching only line 1 — e.g. the store applying
    // fresh disk content that still contains the user's edit.
    handle.setText('ALPHA\nbravo\nxcharlie\n');
    expect(model.getValue()).toBe('ALPHA\nbravo\nxcharlie\n');

    // Cursor survived: the minimal edit never touched line 3.
    expect(editor.getPosition()).toMatchObject({ lineNumber: 3, column: 2 });

    // Undo stack survived: first undo reverts the external update, second
    // reverts the user's own edit.
    model.undo();
    expect(model.getValue()).toBe('alpha\nbravo\nxcharlie\n');
    model.undo();
    expect(model.getValue()).toBe('alpha\nbravo\ncharlie\n');
  });

  it('forces attached editors read-only for non-buffer facets', async () => {
    const binder = newBinder();
    const ref = fileRef('repo', 'ro.txt');
    await createHandle(binder, descriptor(ref, BUFFER, 'text'));
    await createHandle(binder, descriptor(ref, DISK, 'text'));

    const editor = createEditor();
    binder.attach(editor, encodeFacetUri(ref, DISK));
    expect(editor.getOption(monaco.editor.EditorOption.readOnly)).toBe(true);

    binder.attach(editor, encodeFacetUri(ref, BUFFER), encodeFacetUri(ref, DISK));
    expect(editor.getOption(monaco.editor.EditorOption.readOnly)).toBe(false);
  });

  it('applies setText to read-only facets (store-driven updates)', async () => {
    const binder = newBinder();
    const ref = fileRef('repo', 'mirror.txt');
    const handle = await createHandle(binder, descriptor(ref, DISK, 'v1'));
    handle.setText('v2');
    expect(handle.getText()).toBe('v2');
  });

  it('disposes the model on last handle dispose; dispose is idempotent', async () => {
    const binder = newBinder();
    const ref = fileRef('repo', 'dispose.txt');
    const handle = await binder.createHandle(descriptor(ref, BUFFER, 'text'));
    const uri = encodeFacetUri(ref, BUFFER);
    const model = binder.modelFor(uri);
    if (!model) throw new Error('model missing');

    handle.dispose();
    handle.dispose();
    expect(model.isDisposed()).toBe(true);
    expect(binder.modelFor(uri)).toBeUndefined();
    expect(monaco.editor.getModel(monaco.Uri.parse(uri))).toBeNull();
  });

  it('shares the model if two handles land on one URI and disposes only after both release', async () => {
    const binder = newBinder();
    const ref = fileRef('repo', 'shared.txt');
    const first = await binder.createHandle(descriptor(ref, BUFFER, 'text'));
    const second = await binder.createHandle(descriptor(ref, BUFFER, 'text'));
    const uri = encodeFacetUri(ref, BUFFER);
    const model = binder.modelFor(uri);
    if (!model) throw new Error('model missing');

    first.dispose();
    expect(model.isDisposed()).toBe(false);
    second.dispose();
    expect(model.isDisposed()).toBe(true);
  });

  it('rejects createHandle when Monaco fails to initialize', async () => {
    const binder = newBinder(() => Promise.reject(new Error('monaco init failed')));
    await expect(
      binder.createHandle(descriptor(fileRef('repo', 'broken.ts'), BUFFER, 'text'))
    ).rejects.toThrow('monaco init failed');
  });
});

// ---------------------------------------------------------------------------
// View state
// ---------------------------------------------------------------------------

describe('MonacoFacetBinder view state', () => {
  it('saves view state on detach and restores it on re-attach', async () => {
    const binder = newBinder();
    const refA = fileRef('repo', 'a.txt');
    const refB = fileRef('repo', 'b.txt');
    const lines = Array.from({ length: 100 }, (_, i) => `line ${i + 1}`).join('\n');
    await createHandle(binder, descriptor(refA, BUFFER, lines));
    await createHandle(binder, descriptor(refB, BUFFER, 'short'));
    const uriA = encodeFacetUri(refA, BUFFER);
    const uriB = encodeFacetUri(refB, BUFFER);

    const editor = createEditor();
    binder.attach(editor, uriA);
    editor.setPosition({ lineNumber: 42, column: 4 });
    editor.setScrollTop(300);

    // Switching to B saves A's state; switching back restores it.
    binder.attach(editor, uriB, uriA);
    expect(editor.getPosition()).not.toMatchObject({ lineNumber: 42, column: 4 });
    binder.attach(editor, uriA, uriB);
    expect(editor.getPosition()).toMatchObject({ lineNumber: 42, column: 4 });
    expect(editor.getScrollTop()).toBe(300);

    // detach also saves, so a re-attach after detach restores too.
    editor.setPosition({ lineNumber: 7, column: 2 });
    binder.detach(editor, uriA);
    expect(editor.getModel()).toBeNull();
    binder.attach(editor, uriA);
    expect(editor.getPosition()).toMatchObject({ lineNumber: 7, column: 2 });
  });

  it('saves and restores diff-editor view states keyed by the model pair', async () => {
    const binder = newBinder();
    const ref = fileRef('repo', 'diff.txt');
    const lines = Array.from({ length: 60 }, (_, i) => `line ${i + 1}`).join('\n');
    await createHandle(binder, descriptor(ref, { kind: 'git', ref: { kind: 'head' } }, lines));
    await createHandle(binder, descriptor(ref, BUFFER, `${lines}\nplus`));
    const originalUri = encodeFacetUri(ref, { kind: 'git', ref: { kind: 'head' } });
    const modifiedUri = encodeFacetUri(ref, BUFFER);
    const original = binder.modelFor(originalUri);
    const modified = binder.modelFor(modifiedUri);
    if (!original || !modified) throw new Error('models missing');

    const diffEditor = createDiffEditor();
    diffEditor.setModel({ original, modified });
    diffEditor.getModifiedEditor().setPosition({ lineNumber: 25, column: 3 });
    binder.saveDiffViewState(originalUri, modifiedUri, diffEditor);

    diffEditor.getModifiedEditor().setPosition({ lineNumber: 1, column: 1 });
    binder.restoreDiffViewState(originalUri, modifiedUri, diffEditor);
    expect(diffEditor.getModifiedEditor().getPosition()).toMatchObject({
      lineNumber: 25,
      column: 3,
    });
  });
});

// ---------------------------------------------------------------------------
// Store integration — the binder driving real Monaco models under OpenFileStore
// ---------------------------------------------------------------------------

function textContent(content: string, etag: string): FileContentModel {
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

function storeSetup() {
  const cells = new Map<string, Cell<FileContentModel | undefined>>();
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
    { content: (key) => cellFor(key) },
    {
      lingerMs: 0,
      mutations: {
        write: async () => ok(undefined),
      },
    }
  );
  const testContract = defineContract({ content: filesWireContract.content });
  // Explicit policy: the default reads process.env, which browsers lack.
  const wire = createTestWire(testContract, { content: provider }, { validate: 'full' });
  wireClient.current = wire.client;

  const publish = (ref: HostFileRef, value: FileContentModel) => {
    cellFor({ uri: encodeResourceUri(ref), source: 'disk' }).set(value);
  };
  return { publish };
}

describe('OpenFileStore over MonacoFacetBinder', () => {
  afterEach(() => {
    wireClient.current = undefined;
  });

  it('flows disk updates into the Monaco model and buffer edits back into the store', async () => {
    const { publish } = storeSetup();
    const store = new OpenFileStore();
    cleanups.push(() => store.dispose());
    store.registerBinder(newBinder());

    const ref = fileRef('repo', 'integration.txt');
    const bufferLease = store.acquire(ref, BUFFER);
    store.acquire(ref, DISK);
    publish(ref, textContent('first\n', 'e1'));
    await waitFor(() => bufferLease.entry.status.kind === 'ready');
    await waitFor(() => bufferLease.entry.handleFor(BUFFER) !== undefined);

    const bufferModel = monaco.editor.getModel(monaco.Uri.parse(encodeFacetUri(ref, BUFFER)));
    const diskModel = monaco.editor.getModel(monaco.Uri.parse(encodeFacetUri(ref, DISK)));
    if (!bufferModel || !diskModel) throw new Error('models missing');
    expect(bufferModel.getValue()).toBe('first\n');
    expect(diskModel.getValue()).toBe('first\n');

    // External disk change flows through the store into both models.
    publish(ref, textContent('second\n', 'e2'));
    await waitFor(() => bufferModel.getValue() === 'second\n');
    expect(diskModel.getValue()).toBe('second\n');
    expect(bufferLease.entry.dirty).toBe(false);

    // A user edit on the Monaco buffer reports back synchronously: the store
    // flags dirty before the edit call returns.
    bufferModel.applyEdits([{ range: bufferModel.getFullModelRange().collapseToEnd(), text: '!' }]);
    expect(bufferLease.entry.dirty).toBe(true);
  });

  it('degrades entries to error placeholders when Monaco init fails, leaving the store functional', async () => {
    const { publish } = storeSetup();
    const store = new OpenFileStore();
    cleanups.push(() => store.dispose());

    // First load attempt: Monaco init fails. Later attempts succeed —
    // simulating a transient bootstrap failure.
    let attempts = 0;
    store.registerBinder(
      newBinder(() => {
        attempts += 1;
        return attempts <= 2
          ? Promise.reject(new Error('monaco init failed'))
          : Promise.resolve(monaco);
      })
    );

    const ref = fileRef('repo', 'degraded.txt');
    const lease = store.acquire(ref, BUFFER);
    publish(ref, textContent('body', 'e1'));
    await waitFor(() => lease.entry.status.kind === 'error');
    expect(lease.entry.status).toEqual({ kind: 'error', code: 'unavailable' });

    // Another file degrades independently — nothing is wedged.
    const otherRef = fileRef('repo', 'also-degraded.txt');
    const otherLease = store.acquire(otherRef, BUFFER);
    publish(otherRef, textContent('other', 'e1'));
    await waitFor(() => otherLease.entry.status.kind === 'error');
    otherLease.release();

    // Failed loads are never cached: release drops the errored entry and a
    // re-acquire retries, succeeding once Monaco loads.
    lease.release();
    const retryLease = store.acquire(ref, BUFFER);
    await waitFor(() => retryLease.entry.status.kind === 'ready');
    await waitFor(() => retryLease.entry.handleFor(BUFFER) !== undefined);
    expect(retryLease.entry.handleFor(BUFFER)?.getText()).toBe('body');
  });
});
