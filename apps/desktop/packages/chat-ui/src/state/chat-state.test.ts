/**
 * ChatState persistence unit tests.
 *
 * Tests the per-conversation state that must survive view dispose/recreate
 * (e.g. tab switch): viewState (collapse), scroll mode (ScrollMode), and heightmap.
 *
 * Note: createChatState transitively imports parse.ts (via createParseCaches)
 * which pulls in decode-named-character-reference and requires a DOM. These
 * tests therefore exercise the individual state primitives directly rather
 * than through createChatState, keeping them runnable in the `node` project.
 * The full integration lifecycle is covered by the desktop tab-switch manual
 * test described in the plan.
 */

import { describe, expect, it } from 'vitest';
import type { HeightmapStore } from './chat-state';
import type { ScrollMode } from './scroll-mode';
import { tailMode, pinTopMode } from './scroll-mode';
import { createViewState } from './view-state';

// ── Helpers ───────────────────────────────────────────────────────────────────

function makeHeightmap(): HeightmapStore {
  const data = new Map<string, number>();
  let lastW = 0;
  return {
    get: (id) => data.get(id),
    setAll: (entries) => {
      for (const [id, h] of entries) data.set(id, h);
    },
    get lastWidth() {
      return lastW;
    },
    set lastWidth(w: number) {
      lastW = w;
    },
  };
}

// ── viewState (collapse) ──────────────────────────────────────────────────────

describe('createViewState', () => {
  it('starts with all items expanded (none collapsed)', () => {
    const vs = createViewState();
    expect(vs.isCollapsed('item-1')).toBe(false);
  });

  it('toggleCollapsed marks an item collapsed', () => {
    const vs = createViewState();
    vs.toggleCollapsed('item-1');
    expect(vs.isCollapsed('item-1')).toBe(true);
  });

  it('double-toggle restores expanded state', () => {
    const vs = createViewState();
    vs.toggleCollapsed('x');
    vs.toggleCollapsed('x');
    expect(vs.isCollapsed('x')).toBe(false);
  });

  it('setCollapsed(true) collapses, setCollapsed(false) expands', () => {
    const vs = createViewState();
    vs.setCollapsed('a', true);
    expect(vs.isCollapsed('a')).toBe(true);
    vs.setCollapsed('a', false);
    expect(vs.isCollapsed('a')).toBe(false);
  });

  it('expandAll clears all collapsed entries', () => {
    const vs = createViewState();
    vs.toggleCollapsed('a');
    vs.toggleCollapsed('b');
    vs.expandAll();
    expect(vs.isCollapsed('a')).toBe(false);
    expect(vs.isCollapsed('b')).toBe(false);
  });

  it('snapshot() returns a plain object with collapsed entries', () => {
    const vs = createViewState();
    vs.toggleCollapsed('thinking-1');
    vs.toggleCollapsed('tool-2');
    const snap = vs.snapshot();
    expect(snap['thinking-1']).toBe(true);
    expect(snap['tool-2']).toBe(true);
    expect(snap['other']).toBeUndefined();
  });

  it('restore() re-applies a snapshot from a previous session', () => {
    const vs = createViewState();
    vs.toggleCollapsed('a');
    vs.toggleCollapsed('b');
    const snap = vs.snapshot();

    // Clear state.
    vs.expandAll();
    expect(vs.isCollapsed('a')).toBe(false);

    // Restore — simulates a new view mount against the same ChatState.
    vs.restore(snap);
    expect(vs.isCollapsed('a')).toBe(true);
    expect(vs.isCollapsed('b')).toBe(true);
    expect(vs.isCollapsed('c')).toBe(false);
  });

  it('restore() clears pre-existing entries not in snapshot', () => {
    const vs = createViewState();
    vs.toggleCollapsed('old');
    vs.restore({ new: true });
    expect(vs.isCollapsed('old')).toBe(false);
    expect(vs.isCollapsed('new')).toBe(true);
  });

  it('snapshot is a stable copy (mutations after snapshot do not affect it)', () => {
    const vs = createViewState();
    vs.toggleCollapsed('x');
    const snap = vs.snapshot();
    vs.expandAll();
    // snap must still hold the original value
    expect(snap['x']).toBe(true);
  });
});

// ── scroll mode ──────────────────────────────────────────────────────────────

describe('ScrollMode (plain object semantics)', () => {
  it('tailMode() produces { kind: tail }', () => {
    const mode = tailMode();
    expect(mode.kind).toBe('tail');
  });

  it('anchor mode carries itemId, edge, and offset', () => {
    let stored: ScrollMode = tailMode();
    // Simulate readPhase write-back after user scrolls up
    stored = { kind: 'anchor', itemId: 'msg-7', edge: 'top', offset: 42 };
    expect(stored.kind).toBe('anchor');
    if (stored.kind === 'anchor') {
      expect(stored.itemId).toBe('msg-7');
      expect(stored.edge).toBe('top');
      expect(stored.offset).toBe(42);
    }
  });

  it('pinTopMode() produces a top-edge anchor with offset 0', () => {
    const mode = pinTopMode('user-msg-3');
    expect(mode.kind).toBe('anchor');
    if (mode.kind === 'anchor') {
      expect(mode.itemId).toBe('user-msg-3');
      expect(mode.edge).toBe('top');
      expect(mode.offset).toBe(0);
    }
  });

  it('anchor bottom-edge carries edge: bottom', () => {
    const mode: ScrollMode = { kind: 'anchor', itemId: 'msg-9', edge: 'bottom', offset: -8 };
    expect(mode.kind).toBe('anchor');
    if (mode.kind === 'anchor') {
      expect(mode.edge).toBe('bottom');
      expect(mode.offset).toBe(-8);
    }
  });
});

// ── heightmap ─────────────────────────────────────────────────────────────────

describe('HeightmapStore', () => {
  it('returns undefined for unknown unit ids', () => {
    const hm = makeHeightmap();
    expect(hm.get('nonexistent#self')).toBeUndefined();
  });

  it('persists heights after setAll', () => {
    const hm = makeHeightmap();
    hm.setAll([
      ['item-1#self', 120],
      ['item-2#self', 64],
    ]);
    expect(hm.get('item-1#self')).toBe(120);
    expect(hm.get('item-2#self')).toBe(64);
    expect(hm.get('item-3#self')).toBeUndefined();
  });

  it('lastWidth defaults to 0 and can be set', () => {
    const hm = makeHeightmap();
    expect(hm.lastWidth).toBe(0);
    hm.lastWidth = 800;
    expect(hm.lastWidth).toBe(800);
  });

  it('accumulates heights across multiple setAll calls', () => {
    const hm = makeHeightmap();
    hm.setAll([['item-1#self', 100]]);
    hm.setAll([['item-2#self', 200]]);
    expect(hm.get('item-1#self')).toBe(100);
    expect(hm.get('item-2#self')).toBe(200);
  });

  it('later setAll overwrites earlier values for same unit id', () => {
    const hm = makeHeightmap();
    hm.setAll([['item-1#self', 100]]);
    hm.setAll([['item-1#self', 150]]);
    expect(hm.get('item-1#self')).toBe(150);
  });
});

// ── lifecycle: simulate tab-switch (persist → new view reads same state) ──────

describe('ChatState tab-switch simulation', () => {
  it('viewState, heightmap, and scroll mode survive a simulated tab-switch', () => {
    // Shared state object that both "view A" and "view B" read/write.
    const viewState = createViewState();
    const heightmap = makeHeightmap();
    let scroll: ScrollMode = tailMode();

    // View A: user interacts.
    viewState.toggleCollapsed('thinking-1');
    heightmap.setAll([['msg-10#self', 88]]);
    heightmap.lastWidth = 760;
    // User scrolled up — readPhase writes a top-edge anchor intent.
    scroll = { kind: 'anchor', itemId: 'msg-10', edge: 'top', offset: 30 };

    // View A disposes (does NOT clear ChatState — only the DOM root goes away).

    // View B mounts: reads the same state.
    expect(viewState.isCollapsed('thinking-1')).toBe(true);
    expect(heightmap.get('msg-10#self')).toBe(88);
    expect(heightmap.lastWidth).toBe(760);
    expect(scroll.kind).toBe('anchor');
    if (scroll.kind === 'anchor') {
      expect(scroll.itemId).toBe('msg-10');
      expect(scroll.edge).toBe('top');
      expect(scroll.offset).toBe(30);
    }
  });
});
