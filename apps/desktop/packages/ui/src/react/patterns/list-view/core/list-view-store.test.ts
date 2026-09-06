import { observable, runInAction } from 'mobx';
import { describe, expect, it, vi } from 'vitest';
import { byField } from '../comparators';
import { createTextMatcher } from '../matching';
import { ListViewStore } from './list-view-store';
import type { ListViewSpec } from './types';

// ── Fixtures ──────────────────────────────────────────────────────────────────

interface Agent {
  id: string;
  name: string;
  status: 'installed' | 'not-installed';
}

const AGENTS: Agent[] = [
  { id: '1', name: 'Claude Sonnet', status: 'installed' },
  { id: '2', name: 'OpenAI Codex', status: 'installed' },
  { id: '3', name: 'Gemini', status: 'not-installed' },
  { id: '4', name: 'Aider', status: 'not-installed' },
];

const baseSpec: ListViewSpec<Agent> = {
  getItemId: (a) => a.id,
  source: { kind: 'sync', items: AGENTS },
};

// ── Tests ─────────────────────────────────────────────────────────────────────

describe('ListViewStore — sync pipeline', () => {
  it('exposes raw items as visibleItems when no capabilities are configured', () => {
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(baseSpec);
    expect(store.visibleItems).toEqual(AGENTS);
    expect(store.orderedIds).toEqual(['1', '2', '3', '4']);
  });

  it('filters by search activeQuery (sync)', () => {
    const spec: ListViewSpec<Agent> = {
      ...baseSpec,
      search: {
        kind: 'sync',
        predicate: createTextMatcher((a: Agent) => a.name),
        debounceMs: 0,
      },
    };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);
    store.search!.setQuery('claude');
    expect(store.visibleItems).toEqual([AGENTS[0]]);
  });

  it('filters by filter model (sync)', () => {
    type F = { status: 'all' | 'installed' | 'not-installed' };
    const spec: ListViewSpec<Agent> = {
      ...baseSpec,
      filter: {
        kind: 'sync',
        initial: { status: 'all' as F['status'] },
        apply: (a: Agent, f: F) => f.status === 'all' || a.status === f.status,
      },
    };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);
    expect(store.visibleItems).toHaveLength(4);
    store.filter!.set({ status: 'installed' });
    expect(store.visibleItems.map((a: Agent) => a.id)).toEqual(['1', '2']);
    store.filter!.reset();
    expect(store.visibleItems).toHaveLength(4);
  });

  it('sorts with a comparator (sync)', () => {
    const spec: ListViewSpec<Agent> = {
      ...baseSpec,
      sort: {
        keys: { name: { label: 'Name', compare: byField<Agent>((a) => a.name) } },
        initial: { key: 'name', dir: 'asc' },
      },
    };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);
    expect(store.visibleItems.map((a: Agent) => a.name)).toEqual([
      'Aider',
      'Claude Sonnet',
      'Gemini',
      'OpenAI Codex',
    ]);
    store.sort!.toggleDir();
    expect((store.visibleItems[0] as Agent).name).toBe('OpenAI Codex');
  });

  it('groups into sections', () => {
    const spec: ListViewSpec<Agent> = {
      ...baseSpec,
      sections: { by: (a: Agent) => a.status },
    };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);
    const sections = store.sections!;
    expect(sections).toHaveLength(2);
    expect(sections[0]!.key).toBe('installed');
    expect(sections[0]!.items).toHaveLength(2);
  });

  it('groups sections in declared order', () => {
    const spec: ListViewSpec<Agent> = {
      ...baseSpec,
      sections: {
        by: (a: Agent) => a.status,
        order: ['not-installed', 'installed'],
      },
    };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);
    expect(store.sections![0]!.key).toBe('not-installed');
    expect(store.orderedIds).toEqual(['3', '4', '1', '2']);
  });
});

describe('ListViewStore — selection', () => {
  it('single selection — toggle replaces', () => {
    const spec: ListViewSpec<Agent> = { ...baseSpec, selection: { kind: 'single' } };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);
    store.selectionSlice!.toggle('1');
    expect(store.selectionSlice!.selectedIds.has('1')).toBe(true);
    store.selectionSlice!.toggle('2');
    expect(store.selectionSlice!.selectedIds.has('1')).toBe(false);
    expect(store.selectionSlice!.selectedIds.has('2')).toBe(true);
  });

  it('multi selection — shift-range', () => {
    const spec: ListViewSpec<Agent> = { ...baseSpec, selection: { kind: 'multi' } };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);
    store.selectionSlice!.toggle('1');
    store.selectionSlice!.selectRange('1', '3', store.orderedIds);
    expect([...store.selectionSlice!.selectedIds].sort()).toEqual(['1', '2', '3']);
  });

  it('multi selection — reversing a range contracts it', () => {
    const spec: ListViewSpec<Agent> = { ...baseSpec, selection: { kind: 'multi' } };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);
    store.selectionSlice!.toggle('1');
    store.selectionSlice!.selectRange('1', '4', store.orderedIds);
    store.selectionSlice!.selectRange('1', '3', store.orderedIds);
    expect([...store.selectionSlice!.selectedIds].sort()).toEqual(['1', '2', '3']);
  });

  it('selectAll / clear', () => {
    const spec: ListViewSpec<Agent> = { ...baseSpec, selection: { kind: 'multi' } };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);
    store.selectionSlice!.selectAll(store.orderedIds);
    expect(store.selectionSlice!.selectedIds.size).toBe(4);
    store.selectionSlice!.clear();
    expect(store.selectionSlice!.selectedIds.size).toBe(0);
  });
});

describe('ListViewStore — async pipeline', () => {
  it('runs async search and populates items', async () => {
    const search = vi.fn(async (query: string) =>
      AGENTS.filter((a) => a.name.toLowerCase().includes(query.toLowerCase()))
    );
    const spec: ListViewSpec<Agent> = {
      ...baseSpec,
      search: { kind: 'async', search, debounceMs: 0 },
    };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);
    store.initialize();

    // Initial async reaction fires (empty query).
    await new Promise((r) => setTimeout(r, 0));

    store.search!.setQuery('claude');
    await new Promise((r) => setTimeout(r, 20));

    expect(store.visibleItems).toEqual([AGENTS[0]]);
    expect(store.status).toBe('idle');
  });
});

describe('ListViewStore — reload', () => {
  it('loads page one once when an async source also has pagination', async () => {
    const loadSource = vi.fn(async () => AGENTS);
    const loadMore = vi.fn(async () => ({ items: [AGENTS[0]!], nextCursor: null }));
    const spec: ListViewSpec<Agent> = {
      getItemId: (agent) => agent.id,
      source: { kind: 'async', load: loadSource },
      pagination: { kind: 'infinite', loadMore },
    };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);

    store.initialize();

    await vi.waitFor(() => expect(loadMore).toHaveBeenCalledTimes(1));
    expect(loadSource).not.toHaveBeenCalled();
    expect(loadMore).toHaveBeenCalledWith(null, expect.any(AbortSignal));
    store.dispose();
  });

  it('aborts the current page, clears accumulation, and loads page one', async () => {
    const requests: Array<{
      cursor: string | null;
      signal: AbortSignal;
      resolve: (page: { items: Agent[]; nextCursor: string | null }) => void;
    }> = [];
    const spec: ListViewSpec<Agent> = {
      ...baseSpec,
      pagination: {
        kind: 'infinite',
        loadMore: (cursor, signal) =>
          new Promise((resolve) => {
            requests.push({ cursor, signal, resolve });
          }),
      },
    };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);
    store.initialize();
    await vi.waitFor(() => expect(requests).toHaveLength(1));

    const reload = store.reload();
    await vi.waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[0]!.signal.aborted).toBe(true);
    expect(requests[1]!.cursor).toBeNull();

    requests[1]!.resolve({ items: [AGENTS[2]!], nextCursor: null });
    await reload;
    expect(store.visibleItems).toEqual([AGENTS[2]]);
    store.dispose();
  });

  it('surfaces pagination failures through list status', async () => {
    const failure = new Error('Unable to load page');
    const spec: ListViewSpec<Agent> = {
      ...baseSpec,
      pagination: {
        kind: 'infinite',
        loadMore: async () => await Promise.reject(failure),
      },
    };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);

    store.initialize();

    await vi.waitFor(() => expect(store.status).toBe('error'));
    expect(store.error).toBe(failure);
    store.dispose();
  });

  it('aborts replaced async sources and resolves after the pipeline completes', async () => {
    const requests: Array<{
      signal: AbortSignal;
      resolve: (items: Agent[]) => void;
    }> = [];
    const spec: ListViewSpec<Agent> = {
      getItemId: (agent) => agent.id,
      source: {
        kind: 'async',
        load: (signal) =>
          new Promise((resolve) => {
            requests.push({ signal, resolve });
          }),
      },
    };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);
    store.initialize();
    await vi.waitFor(() => expect(requests).toHaveLength(1));

    const reload = store.reload();
    await vi.waitFor(() => expect(requests).toHaveLength(2));
    expect(requests[0]!.signal.aborted).toBe(true);
    requests[1]!.resolve([AGENTS[1]!]);

    await reload;
    expect(store.visibleItems).toEqual([AGENTS[1]]);
    expect(store.status).toBe('idle');
    store.dispose();
  });
});

describe('ListViewStore — reactive sync source', () => {
  it('updates visibleItems when the getter result changes', () => {
    const items: Agent[] = [AGENTS[0]!, AGENTS[1]!];
    const spec: ListViewSpec<Agent> = {
      getItemId: (a) => a.id,
      source: { kind: 'sync', items: () => items },
    };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);
    expect(store.visibleItems).toHaveLength(2);
    items.push(AGENTS[2]!);
    // The getter is re-called on each computed access.
    expect(store.visibleItems).toHaveLength(3);
  });
});

describe('ListViewStore — external source', () => {
  interface ExternalState {
    items: Agent[];
    status: 'idle' | 'loading' | 'error';
    error: unknown;
  }

  function createExternalStore(initial: Partial<ExternalState> = {}) {
    const state = observable.object<ExternalState>(
      { items: [], status: 'loading', error: undefined, ...initial },
      { items: observable.ref },
      { deep: false }
    );
    const spec: ListViewSpec<Agent> = {
      getItemId: (a) => a.id,
      source: {
        kind: 'external',
        items: () => state.items,
        status: () => state.status,
        error: () => state.error,
      },
    };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);
    return { store, state };
  }

  it('mirrors status and error from the external getters after initialize', () => {
    const { store, state } = createExternalStore();
    store.initialize();

    expect(store.status).toBe('loading');

    runInAction(() => {
      state.items = AGENTS;
      state.status = 'idle';
    });
    expect(store.status).toBe('idle');
    expect(store.visibleItems).toEqual(AGENTS);

    const failure = new Error('boom');
    runInAction(() => {
      state.status = 'error';
      state.error = failure;
    });
    expect(store.status).toBe('error');
    expect(store.error).toBe(failure);

    // Leaving the error state clears the mirrored error.
    runInAction(() => {
      state.status = 'idle';
    });
    expect(store.error).toBeUndefined();

    store.dispose();
  });

  it('keeps items visible while status is error (stale rows on refetch failure)', () => {
    const { store, state } = createExternalStore({ items: AGENTS, status: 'idle' });
    store.initialize();

    runInAction(() => {
      state.status = 'error';
      state.error = new Error('refetch failed');
    });
    expect(store.status).toBe('error');
    expect(store.visibleItems).toEqual(AGENTS);

    store.dispose();
  });

  it('runs the sync pipeline over external items', () => {
    const state = observable.object(
      { items: AGENTS, status: 'idle' as const },
      { items: observable.ref },
      { deep: false }
    );
    const spec: ListViewSpec<Agent> = {
      getItemId: (a) => a.id,
      source: { kind: 'external', items: () => state.items, status: () => state.status },
      search: {
        kind: 'sync',
        predicate: createTextMatcher((a: Agent) => a.name),
        debounceMs: 0,
      },
    };
    const store = new ListViewStore<Agent, ListViewSpec<Agent>>(spec);
    store.initialize();

    store.search!.setQuery('claude');
    expect(store.visibleItems).toEqual([AGENTS[0]]);

    store.dispose();
  });

  it('stops mirroring after dispose and reload is a no-op', async () => {
    const { store, state } = createExternalStore({ items: AGENTS, status: 'idle' });
    store.initialize();

    await store.reload();
    expect(store.status).toBe('idle');

    store.dispose();
    runInAction(() => {
      state.status = 'error';
      state.error = new Error('after dispose');
    });
    expect(store.status).toBe('idle');
    expect(store.error).toBeUndefined();
  });
});
