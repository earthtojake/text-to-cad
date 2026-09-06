/**
 * Smoke tests for split-pane size persistence through the shared layout
 * storage (spec: pane-layout ownership). The library's `useDefaultLayout`
 * derives the storage entry key from the pane-group id combination, which is
 * what gives us stale-layout tolerance for free: a persisted layout whose
 * pane set changed (group destroyed, task re-split) is simply never read,
 * and the panes fall back to their default sizes.
 */
import { useResizableDefaultLayout, type LayoutStorage } from '@emdash/ui/react/primitives';
import { JSDOM } from 'jsdom';
import React, { act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { splitPanePanelId } from '@core/features/tasks/contributions/mementos';

(
  globalThis as typeof globalThis & { IS_REACT_ACT_ENVIRONMENT?: boolean }
).IS_REACT_ACT_ENVIRONMENT = true;

class MemoryStorage implements LayoutStorage {
  readonly map = new Map<string, string>();
  getItem = (key: string): string | null => this.map.get(key) ?? null;
  setItem = (key: string, value: string): void => {
    this.map.set(key, value);
  };
}

const paneA = 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa';
const paneB = 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb';
const paneC = 'cccccccc-cccc-4ccc-8ccc-cccccccccccc';

const entryKey = (...paneIds: string[]) =>
  `react-resizable-panels:task-main-split:${paneIds.map(splitPanePanelId).join(':')}`;

let latest: ReturnType<typeof useResizableDefaultLayout> | undefined;

function Probe({ panelIds, storage }: { panelIds: string[]; storage: LayoutStorage }) {
  latest = useResizableDefaultLayout({ id: 'task-main-split', panelIds, storage });
  return null;
}

describe('split-pane layout persistence through the shared storage', () => {
  let dom: JSDOM;
  let root: Root;

  beforeEach(() => {
    dom = new JSDOM('<!doctype html><html><body><div id="root"></div></body></html>');
    globalThis.window = dom.window as unknown as typeof globalThis.window;
    globalThis.document = dom.window.document;
    root = createRoot(dom.window.document.getElementById('root') as HTMLElement);
  });

  afterEach(() => {
    act(() => root.unmount());
    latest = undefined;
    // @ts-expect-error test cleanup of the jsdom globals installed above
    delete globalThis.window;
    // @ts-expect-error test cleanup of the jsdom globals installed above
    delete globalThis.document;
    dom.window.close();
  });

  function render(panelIds: string[], storage: LayoutStorage) {
    act(() => {
      root.render(React.createElement(Probe, { panelIds, storage }));
    });
  }

  it('restores a stored layout for the exact pane-group combination', () => {
    const storage = new MemoryStorage();
    storage.setItem(
      entryKey(paneA, paneB),
      JSON.stringify({ [splitPanePanelId(paneA)]: 70, [splitPanePanelId(paneB)]: 30 })
    );

    render([splitPanePanelId(paneA), splitPanePanelId(paneB)], storage);

    expect(latest?.defaultLayout).toEqual({
      [splitPanePanelId(paneA)]: 70,
      [splitPanePanelId(paneB)]: 30,
    });
  });

  it('degrades to defaults when the pane-group combination changed (stale layout)', () => {
    const storage = new MemoryStorage();
    storage.setItem(
      entryKey(paneA, paneB),
      JSON.stringify({ [splitPanePanelId(paneA)]: 70, [splitPanePanelId(paneB)]: 30 })
    );

    // Pane B was destroyed and a re-split created pane C: the stale two-pane
    // entry must not leak into the new combination.
    render([splitPanePanelId(paneA), splitPanePanelId(paneC)], storage);

    expect(latest?.defaultLayout).toBeUndefined();
  });

  it('persists a settled drag layout under the combination-derived entry key', () => {
    const storage = new MemoryStorage();
    render([splitPanePanelId(paneA), splitPanePanelId(paneB)], storage);

    act(() => {
      latest?.onLayoutChanged({
        [splitPanePanelId(paneA)]: 60,
        [splitPanePanelId(paneB)]: 40,
      });
    });

    expect(storage.getItem(entryKey(paneA, paneB))).toBe(
      JSON.stringify({ [splitPanePanelId(paneA)]: 60, [splitPanePanelId(paneB)]: 40 })
    );
  });
});
