/**
 * @vitest-environment jsdom
 */
import { cleanup, render, renderHook } from '@testing-library/react';
import { autorun } from 'mobx';
import { afterEach, describe, expect, it } from 'vitest';
import { ListViewStore } from './core/list-view-store';
import type { ListViewSpec } from './core/types';
import { useQueryListSource, type QueryResultLike } from './use-query-list-source';

interface Row {
  id: string;
  name: string;
}

const ROWS: Row[] = [
  { id: '1', name: 'Alpha' },
  { id: '2', name: 'Beta' },
];

function query(overrides: Partial<QueryResultLike<Row[]>> = {}): QueryResultLike<Row[]> {
  return { data: undefined, isLoading: false, isError: false, error: null, ...overrides };
}

function storeFor(source: ReturnType<typeof useQueryListSource<Row[], Row>>) {
  const spec: ListViewSpec<Row> = { getItemId: (row) => row.id, source };
  const store = new ListViewStore<Row, ListViewSpec<Row>>(spec);
  store.initialize();
  return store;
}

afterEach(cleanup);

describe('useQueryListSource', () => {
  it('is seeded from the first render — cached data never flashes empty', () => {
    // Capture during the render phase itself, before any effect (layout or
    // passive) can run: the useState initializer alone must hold the data.
    let itemsDuringFirstRender: Row[] | null = null;
    let statusDuringFirstRender: string | null = null;

    function Probe() {
      const source = useQueryListSource(query({ data: ROWS }), (rows: Row[]) => rows);
      if (itemsDuringFirstRender === null) {
        itemsDuringFirstRender = source.items();
        statusDuringFirstRender = source.status();
      }
      return null;
    }

    render(<Probe />);
    expect(itemsDuringFirstRender).toEqual(ROWS);
    expect(statusDuringFirstRender).toBe('idle');
  });

  it('mirrors loading, ready, and error transitions into a view store', () => {
    const { result, rerender } = renderHook(
      (props) => useQueryListSource(props.query, props.build),
      {
        initialProps: { query: query({ isLoading: true }), build: (rows: Row[]) => rows },
      }
    );
    const store = storeFor(result.current);

    // Reactions only see changes they observe; keep the store's mirror hot the
    // way `Root` + observer components do in the app.
    const stop = autorun(() => {
      void store.status;
      void store.visibleItems;
    });

    expect(store.status).toBe('loading');
    expect(store.visibleItems).toEqual([]);

    rerender({ query: query({ data: ROWS }), build: (rows: Row[]) => rows });
    expect(store.status).toBe('idle');
    expect(store.visibleItems).toEqual(ROWS);

    const failure = new Error('fetch failed');
    rerender({
      query: query({ data: ROWS, isError: true, error: failure }),
      build: (rows: Row[]) => rows,
    });
    expect(store.status).toBe('error');
    expect(store.error).toBe(failure);
    // Stale rows stay visible on refetch failure.
    expect(store.visibleItems).toEqual(ROWS);

    stop();
    store.dispose();
  });

  it('keeps the source referentially stable and ignores value-equal rerenders', () => {
    const build = (rows: Row[]) => rows;
    const { result, rerender } = renderHook(
      (props) => useQueryListSource(props.query, props.build),
      { initialProps: { query: query({ data: ROWS }), build } }
    );

    const source = result.current;
    const store = storeFor(source);
    const stop = autorun(() => void store.visibleItems);
    const visible = store.visibleItems;

    // A new query object with identical values (what React Query returns on
    // unrelated rerenders) must not reset the box or recompute the pipeline.
    rerender({ query: query({ data: ROWS }), build });
    expect(result.current).toBe(source);
    expect(store.visibleItems).toBe(visible);

    stop();
    store.dispose();
  });
});
