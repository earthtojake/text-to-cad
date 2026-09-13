/**
 * @vitest-environment jsdom
 *
 * Regression tests for the two non-obvious react-resizable-panels traps the
 * binding exists to encapsulate (see the hook's doc comments):
 *
 * - The sliver guard: `onLayoutChanged` fires on mount and panel enter/leave
 *   reflows too, so the hook must never persist while the panel is closed and
 *   never persist a sub-threshold size — otherwise reopening restores a sliver.
 * - The generation-id guard ("poisoned panel memory"): a panel re-entering a
 *   still-mounted group under the same id is restored from the library's
 *   in-memory registry, ignoring `defaultLayout`/`defaultSize`. After a
 *   drag-to-close that memory holds the sub-threshold sliver, so a naive
 *   reopen instantly re-closes. The hook must hand out a fresh
 *   generation-suffixed panel id after each threshold close, and strip the
 *   suffix before persisting so storage keys stay stable.
 */
import { act, renderHook } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { useCollapsiblePanelBinding, type LayoutStorage } from './use-collapsible-panel-binding';

class MemoryStorage implements LayoutStorage {
  readonly map = new Map<string, string>();
  getItem = (key: string): string | null => this.map.get(key) ?? null;
  setItem = (key: string, value: string): void => {
    this.map.set(key, value);
  };
}

// Library-internal key format: `react-resizable-panels:${id}:${...panelIds}`.
const STORAGE_KEY = 'react-resizable-panels:test-group:main:side';

function setup({ open = true }: { open?: boolean } = {}) {
  const storage = new MemoryStorage();
  const onCloseRequest = vi.fn();
  const view = renderHook(
    (props: { open: boolean }) =>
      useCollapsiblePanelBinding({
        storageKey: 'test-group',
        storage,
        panelIds: ['main', 'side'],
        collapsiblePanelId: 'side',
        open: props.open,
        onCloseRequest,
        closeThreshold: 8,
      }),
    { initialProps: { open } }
  );
  return { storage, onCloseRequest, view };
}

describe('useCollapsiblePanelBinding', () => {
  it('persists a settled drag layout under the stable storage key', () => {
    const { storage, view } = setup();

    act(() => view.result.current.groupProps.onLayoutChanged({ main: 70, side: 30 }));

    expect(storage.getItem(STORAGE_KEY)).toBe(JSON.stringify({ main: 70, side: 30 }));
  });

  describe('sliver guard', () => {
    it('requests close instead of persisting when a drag settles below the threshold', () => {
      const { storage, onCloseRequest, view } = setup();

      act(() => view.result.current.groupProps.onLayoutChanged({ main: 70, side: 30 }));
      act(() => view.result.current.groupProps.onLayoutChanged({ main: 96, side: 4 }));

      expect(onCloseRequest).toHaveBeenCalledTimes(1);
      // The sub-threshold sliver must never be persisted; the last good size stays.
      expect(storage.getItem(STORAGE_KEY)).toBe(JSON.stringify({ main: 70, side: 30 }));
    });

    it('requests close when the library snaps a collapsible panel to its 0% collapsedSize', () => {
      const { storage, onCloseRequest, view } = setup();

      act(() => view.result.current.groupProps.onLayoutChanged({ main: 70, side: 30 }));
      // Hosts that set `minSize` + `collapsible` + `collapsedSize="0%"` never
      // settle at intermediate slivers: dragging below `minSize` makes the
      // library snap the layout straight to 0.
      act(() => view.result.current.groupProps.onLayoutChanged({ main: 100, side: 0 }));

      expect(onCloseRequest).toHaveBeenCalledTimes(1);
      // The snapped-to-0 layout must never be persisted; the last good size stays.
      expect(storage.getItem(STORAGE_KEY)).toBe(JSON.stringify({ main: 70, side: 30 }));
    });

    it('never persists layouts reported while closed (mount/unmount reflows)', () => {
      const { storage, onCloseRequest, view } = setup({ open: false });

      act(() => view.result.current.groupProps.onLayoutChanged({ main: 100 }));

      expect(onCloseRequest).not.toHaveBeenCalled();
      expect(storage.map.size).toBe(0);
    });

    it('restores the last good size when reopening after a threshold close', () => {
      const { view } = setup();

      act(() => view.result.current.groupProps.onLayoutChanged({ main: 70, side: 30 }));
      act(() => view.result.current.groupProps.onLayoutChanged({ main: 97, side: 3 }));
      view.rerender({ open: false });
      view.rerender({ open: true });

      expect(view.result.current.collapsiblePanelProps.defaultSize).toBe('30%');
    });
  });

  describe('generation-id guard', () => {
    it('uses the canonical panel id before any threshold close', () => {
      const { view } = setup();
      expect(view.result.current.collapsiblePanelProps.id).toBe('side');
    });

    it('hands out a fresh generation-suffixed id after each threshold close', () => {
      const { view } = setup();

      act(() => view.result.current.groupProps.onLayoutChanged({ main: 95, side: 5 }));
      view.rerender({ open: false });
      view.rerender({ open: true });
      const firstReopenId = view.result.current.collapsiblePanelProps.id;

      act(() => view.result.current.groupProps.onLayoutChanged({ main: 95, [firstReopenId]: 5 }));
      view.rerender({ open: false });
      view.rerender({ open: true });
      const secondReopenId = view.result.current.collapsiblePanelProps.id;

      expect(firstReopenId).not.toBe('side');
      expect(secondReopenId).not.toBe('side');
      expect(secondReopenId).not.toBe(firstReopenId);
    });

    it('does not bump the generation on a user toggle (no threshold close)', () => {
      const { view } = setup();

      view.rerender({ open: false });
      view.rerender({ open: true });

      expect(view.result.current.collapsiblePanelProps.id).toBe('side');
    });

    it('strips the generation suffix before persisting so storage keys stay stable', () => {
      const { storage, view } = setup();

      act(() => view.result.current.groupProps.onLayoutChanged({ main: 95, side: 5 }));
      view.rerender({ open: false });
      view.rerender({ open: true });
      const generationId = view.result.current.collapsiblePanelProps.id;

      act(() => view.result.current.groupProps.onLayoutChanged({ main: 60, [generationId]: 40 }));

      expect(storage.getItem(STORAGE_KEY)).toBe(JSON.stringify({ main: 60, side: 40 }));
      // No generation-suffixed key or value may ever reach storage.
      for (const [key, value] of storage.map) {
        expect(key).not.toContain(generationId);
        expect(value).not.toContain(generationId);
      }
    });
  });
});
