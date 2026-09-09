import { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { FileContentSearchResults } from './file-content-search';
import '@emdash/ui/style.css';

const mocks = vi.hoisted(() => ({
  result: {
    complete: true,
    files: Array.from({ length: 120 }, (_, index) => ({
      path: `src/search-result-${index}.ts`,
      matches: [
        {
          lineNumber: index + 1,
          previewText: `const searchResult${index} = true;`,
          locations: [
            {
              sourceRange: { startColumn: 1, endColumn: 6 },
              previewRange: { startColumn: 1, endColumn: 6 },
            },
          ],
        },
      ],
    })),
  },
}));

vi.mock('@core/features/search/api/client', () => ({
  getSearchClient: async () => ({}),
}));

vi.mock('@core/features/workbench/api/browser/task-composition-context', () => ({
  useTaskComposition: () => ({
    paneLayout: { open: vi.fn() },
    activePane: { activeResourceOfKind: () => null },
    setFocusedRegion: vi.fn(),
  }),
}));

vi.mock('@core/primitives/react-hooks/browser/useDebounce', () => ({
  useDebounce: (value: unknown) => value,
}));

vi.mock('@emdash/wire/live', () => {
  class LiveJobCancelledError extends Error {}
  class LiveJobFailedError extends Error {
    readonly error: unknown;

    constructor(error: unknown) {
      super('Live job failed');
      this.error = error;
    }
  }

  return {
    LiveJobCancelledError,
    LiveJobFailedError,
    createLiveJobReplicaCache: () => ({
      start: async () => ({
        ready: async () => ({
          cancel: async () => {},
          onProgress: () => () => {},
          result: Promise.resolve(mocks.result),
        }),
        release: async () => {},
      }),
      dispose: async () => {},
    }),
  };
});

beforeAll(() => {
  (
    globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT: boolean }
  ).IS_REACT_ACT_ENVIRONMENT = true;
});

describe('FileContentSearchResults layout', () => {
  let host: HTMLDivElement;
  let root: Root;
  let utilityStyles: HTMLStyleElement;

  beforeEach(() => {
    utilityStyles = document.createElement('style');
    utilityStyles.textContent = `
      .flex { display: flex; }
      .min-h-0 { min-height: 0; }
      .flex-1 { flex: 1 1 0%; }
      .flex-col { flex-direction: column; }
      .overflow-hidden { overflow: hidden; }
      .h-8 { height: 2rem; }
      .shrink-0 { flex-shrink: 0; }
    `;
    document.head.append(utilityStyles);

    host = document.createElement('div');
    host.style.width = '360px';
    document.body.append(host);
    root = createRoot(host);
  });

  afterEach(async () => {
    await act(async () => root.unmount());
    host.remove();
    utilityStyles.remove();
  });

  it('keeps the virtualized results inside a bounded scrollport', async () => {
    await act(async () => {
      root.render(
        <div
          style={{
            display: 'flex',
            height: 260,
            flexDirection: 'column',
            overflow: 'hidden',
          }}
        >
          <div style={{ height: 40, flexShrink: 0 }} />
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <FileContentSearchResults workspaceId="workspace-1" query="const" />
          </div>
        </div>
      );
    });

    await act(async () => {
      await vi.waitFor(() => {
        expect(host.textContent).toContain('120 results in 120 files');
      });
    });

    const tree = host.querySelector<HTMLElement>('[role="tree"]');
    const viewport = tree?.firstElementChild as HTMLElement | undefined;
    expect(tree).not.toBeNull();
    expect(viewport).toBeDefined();
    expect(getComputedStyle(viewport!).overflowY).toBe('auto');
    expect(viewport!.scrollHeight).toBeGreaterThan(viewport!.clientHeight);

    await act(async () => {
      viewport!.scrollTop = 200;
      viewport!.dispatchEvent(new Event('scroll'));
      await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    });
    expect(viewport!.scrollTop).toBeGreaterThan(0);
  });
});
