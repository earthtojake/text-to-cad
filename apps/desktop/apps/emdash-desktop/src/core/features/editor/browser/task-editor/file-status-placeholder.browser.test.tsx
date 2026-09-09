import { observable, runInAction } from 'mobx';
import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import type {
  ContentStatus,
  OpenFileEntry,
  OpenFileLease,
  OpenFileStore,
} from '@core/features/editor/api/browser/open-file-store/open-file-store';
import { FileTabResource } from '@core/features/editor/api/browser/task-editor/stores/file-tab-resource';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import { FileStatusPlaceholder } from './file-status-placeholder';
import '@emdash/ui/style.css';

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

function createFakeStore() {
  const state = observable.object({ status: { kind: 'loading' } as ContentStatus });
  const entry = {
    get status() {
      return state.status;
    },
    dirty: false,
    conflicted: false,
    saving: false,
    handleFor: () => undefined,
    gitStatus: () => undefined,
  } as unknown as OpenFileEntry;

  let acquireCount = 0;
  const store: Pick<OpenFileStore, 'acquire'> = {
    acquire: () => {
      acquireCount += 1;
      return { entry, release: () => {} } as OpenFileLease;
    },
  };

  return {
    store,
    setStatus: (status: ContentStatus) =>
      runInAction(() => {
        state.status = status;
      }),
    get acquireCount() {
      return acquireCount;
    },
  };
}

describe('FileStatusPlaceholder rendering states', () => {
  let host: HTMLDivElement;
  let root: Root;
  let fake: ReturnType<typeof createFakeStore>;
  let resource: FileTabResource;

  beforeEach(() => {
    host = document.createElement('div');
    document.body.append(host);
    root = createRoot(host);
    fake = createFakeStore();
    resource = new FileTabResource(
      { path: '/repo/src/index.ts' },
      { ref: hostFileRefFromNativePath('/repo/src/index.ts'), store: fake.store }
    );
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    resource.dispose();
    host.remove();
  });

  async function render() {
    await act(async () => {
      root.render(<FileStatusPlaceholder resource={resource} />);
    });
  }

  it('shows the bounded loading state', async () => {
    await render();
    expect(host.textContent).toContain('Loading file');
  });

  it('shows the orphaned placeholder and auto-recovers to nothing when ready again', async () => {
    await render();

    await act(async () => fake.setStatus({ kind: 'orphaned' }));
    expect(host.textContent).toContain('File was deleted on disk');

    await act(async () => fake.setStatus({ kind: 'ready' }));
    expect(host.textContent).toBe('');
  });

  it('offers a retry that re-acquires the leases for retryable errors', async () => {
    await render();
    await act(async () => fake.setStatus({ kind: 'error', code: 'not-found' }));
    expect(host.textContent).toContain('File not found');

    const before = fake.acquireCount;
    const retry = [...host.querySelectorAll('button')].find((b) => b.textContent === 'Retry');
    expect(retry).toBeDefined();
    await act(async () => retry!.click());
    expect(fake.acquireCount).toBe(before + 2);
  });

  it('offers open-in-default-app for binary and too-large files', async () => {
    await render();

    await act(async () => fake.setStatus({ kind: 'error', code: 'binary' }));
    expect(host.textContent).toContain('Binary file');
    expect([...host.querySelectorAll('button')].map((b) => b.textContent)).toContain(
      'Open in default app'
    );

    await act(async () => fake.setStatus({ kind: 'error', code: 'too-large' }));
    expect(host.textContent).toContain('File too large');
    expect([...host.querySelectorAll('button')].map((b) => b.textContent)).toContain(
      'Open in default app'
    );
  });
});
