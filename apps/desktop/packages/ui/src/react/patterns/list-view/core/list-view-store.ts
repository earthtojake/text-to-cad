import { computed, makeObservable, observable, reaction, runInAction } from 'mobx';
import type { ListViewSection } from '../virtual-list';
import { FilterSlice } from './capabilities/filter';
import { PaginationSlice } from './capabilities/pagination';
import { RenameSlice } from './capabilities/rename';
import { ScrollSlice } from './capabilities/scroll';
import { SearchSlice } from './capabilities/search';
import { SelectionSlice } from './capabilities/selection';
import { SortSlice } from './capabilities/sort';
import { groupItems, runAsyncPipeline, runSyncPipeline } from './pipeline';
import type { ExternalSelectionStore, FilterModel, ListViewSpec } from './types';

/**
 * ListViewStore — observable state container for a `createListView` instance.
 *
 * Two pipeline paths:
 *
 * **Sync path** (all capabilities and source are sync):
 *   `rawItems` (reactive getter / observable array) →
 *   `_syncResult` (computed) → `visibleItems` (computed).
 *   Any change to a slice's observables triggers automatic re-derivation.
 *
 * **Async path** (any capability or the source is async):
 *   A MobX `reaction` watches all relevant input observables and calls
 *   `runAsyncPipeline`, writing the result into `_asyncPipelineItems`.
 *   A request token drops stale responses.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export class ListViewStore<T, S extends ListViewSpec<any>> {
  // ── Observable state ──────────────────────────────────────────────────────

  /** Holds items loaded by an async source. */
  _asyncSourceItems: T[] = [];
  /** Output written by the async pipeline reaction. */
  _asyncPipelineItems: T[] = [];

  status: 'idle' | 'loading' | 'error' = 'idle';
  error: unknown = undefined;

  // ── Slices ────────────────────────────────────────────────────────────────

  readonly search?: SearchSlice<T>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  readonly filter?: FilterSlice<T, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  readonly sort?: SortSlice<T, any>;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  readonly pagination?: PaginationSlice<any>;
  readonly selectionSlice?: SelectionSlice;
  readonly externalSelection?: ExternalSelectionStore;
  readonly rename?: RenameSlice<T>;
  readonly scroll: ScrollSlice;

  // ── Private ───────────────────────────────────────────────────────────────

  private pipelineToken = 0;
  private sourceToken = 0;
  private pipelineController: AbortController | null = null;
  private sourceController: AbortController | null = null;
  private readonly disposers: Array<() => void> = [];

  constructor(readonly spec: S) {
    this.scroll = new ScrollSlice();

    if (spec.search) {
      (this as { search?: SearchSlice<T> }).search = new SearchSlice(spec.search);
    }
    if (spec.filter) {
      (this as { filter?: FilterSlice<T, FilterModel> }).filter = new FilterSlice(spec.filter);
    }
    if (spec.sort) {
      (this as { sort?: SortSlice<T, string> }).sort = new SortSlice(spec.sort);
    }
    if (spec.pagination) {
      (this as { pagination?: PaginationSlice<T> }).pagination = new PaginationSlice(
        spec.pagination,
        {
          onStart: (isInitialPage) => {
            if (!isInitialPage) return;
            runInAction(() => {
              this.status = 'loading';
              this.error = undefined;
            });
          },
          onSuccess: () => {
            runInAction(() => {
              this.status = 'idle';
              this.error = undefined;
            });
          },
          onError: (error) => {
            runInAction(() => {
              this.status = 'error';
              this.error = error;
            });
          },
        }
      );
    }
    if (spec.selection) {
      if (spec.selection.kind === 'external') {
        (this as { externalSelection?: ExternalSelectionStore }).externalSelection =
          spec.selection.store;
      } else {
        (this as { selectionSlice?: SelectionSlice }).selectionSlice = new SelectionSlice(
          spec.selection.kind
        );
      }
    }
    if (spec.rename) {
      (this as { rename?: RenameSlice<T> }).rename = new RenameSlice(
        spec.rename,
        (id) => this.getItemById(id),
        () => this.orderedIds,
        this.scroll
      );
    }

    makeObservable(this, {
      _asyncSourceItems: observable.ref,
      _asyncPipelineItems: observable.ref,
      status: observable,
      error: observable.ref,
      rawItems: computed,
      _syncResult: computed,
      visibleItems: computed,
      sections: computed,
      orderedIds: computed,
    });
  }

  // ── Computed pipeline ─────────────────────────────────────────────────────

  /**
   * The current source items. For sync sources, this is a reactive read that
   * automatically re-tracks when a getter function reads MobX observables.
   */
  get rawItems(): T[] {
    const src = this.spec.source;
    if (src.kind === 'sync') {
      return typeof src.items === 'function' ? src.items() : src.items;
    }
    if (src.kind === 'external') {
      return src.items();
    }
    return this._asyncSourceItems;
  }

  /** Applies sync stages to `rawItems`. Recalculates automatically when any slice state changes. */
  get _syncResult(): T[] {
    return runSyncPipeline(this.spec, this.rawItems, {
      query: this.search?.activeQuery ?? '',
      filterModel: this.filter?.model as FilterModel | undefined,
      sortKey: this.sort?.key as string | undefined,
      sortDir: (this.sort?.dir ?? 'asc') as 'asc' | 'desc',
    });
  }

  /** True when any pipeline stage requires an async call (constant after construction). */
  get needsAsyncPipeline(): boolean {
    return (
      this.spec.source.kind === 'async' ||
      this.spec.search?.kind === 'async' ||
      this.spec.filter?.kind === 'async' ||
      !!this.spec.sort?.remote
    );
  }

  /** The final visible items after the full pipeline. Feed this to the virtualizer. */
  get visibleItems(): T[] {
    if (this.pagination) {
      return this.pagination.accumulatedItems as T[];
    }
    return this.needsAsyncPipeline ? this._asyncPipelineItems : this._syncResult;
  }

  /**
   * Grouped sections derived from `visibleItems`.
   * Returns `undefined` when no `sections` spec is configured.
   */
  get sections(): ListViewSection<T>[] | undefined {
    if (!this.spec.sections) return undefined;
    const groups = groupItems(this.visibleItems, this.spec.sections.by, this.spec.sections.order);
    return groups.map((g) => ({ key: g.key, items: g.items }));
  }

  /** Flat ordered id list — source of truth for range selection across virtual rows. */
  get orderedIds(): string[] {
    const displayedItems = this.sections
      ? this.sections.flatMap((section) => section.items)
      : this.visibleItems;
    return displayedItems.map(this.spec.getItemId);
  }

  // ── Helpers ───────────────────────────────────────────────────────────────

  getItemById(id: string): T | undefined {
    return this.visibleItems.find((item) => this.spec.getItemId(item) === id);
  }

  /**
   * Re-fetches externally owned data without changing search, filter, or sort state.
   * No-op for `external` sources — their owner (e.g. React Query) handles refetching.
   */
  async reload(): Promise<void> {
    if (this.pagination) {
      await this.pagination.reload();
      return;
    }
    if (this.spec.source.kind === 'async') {
      const loaded = await this.loadSource();
      if (!loaded) return;
    }
    if (this.needsAsyncPipeline) {
      await this.runAsyncPipeline();
    }
  }

  // ── Lifecycle ─────────────────────────────────────────────────────────────

  /**
   * Starts reactions and loads the initial source. Called by `Root` on mount.
   * Do not call more than once.
   */
  initialize(): void {
    if (this.needsAsyncPipeline) {
      this.startAsyncPipelineReaction();
    }
    if (this.spec.source.kind === 'async' && !this.pagination) {
      void this.reload();
    }

    // External sources own fetching; mirror their status/error into the store
    // so the framework's loading/error slots route from `store.status`.
    if (this.spec.source.kind === 'external') {
      const source = this.spec.source;
      const dispose = reaction(
        () => ({ status: source.status(), error: source.error?.() }),
        ({ status, error }) => {
          runInAction(() => {
            this.status = status;
            this.error = status === 'error' ? error : undefined;
          });
        },
        { fireImmediately: true }
      );
      this.disposers.push(dispose);
    }

    // When search/filter/sort changes, reset pagination and load page 1.
    if (this.pagination) {
      const dispose = reaction(
        () => ({
          query: this.search?.activeQuery ?? '',
          filterModel: this.filter ? JSON.stringify(this.filter.model) : '',
          sortKey: this.sort?.key ?? '',
          sortDir: this.sort?.dir ?? 'asc',
        }),
        () => {
          this.pagination!.reset();
          void this.pagination!.loadMore();
        },
        { fireImmediately: true }
      );
      this.disposers.push(dispose);
    }
  }

  private async loadSource(): Promise<boolean> {
    if (this.spec.source.kind !== 'async') return false;
    const token = ++this.sourceToken;
    this.sourceController?.abort();
    const controller = new AbortController();
    this.sourceController = controller;
    runInAction(() => {
      this.status = 'loading';
      this.error = undefined;
    });
    try {
      const items = await this.spec.source.load(controller.signal);
      if (token !== this.sourceToken || controller.signal.aborted) return false;
      runInAction(() => {
        this._asyncSourceItems = items;
        this.status = 'idle';
      });
      return true;
    } catch (e) {
      if (token !== this.sourceToken || controller.signal.aborted || isAbortError(e)) return false;
      runInAction(() => {
        this.status = 'error';
        this.error = e;
      });
      return false;
    } finally {
      if (this.sourceController === controller) this.sourceController = null;
    }
  }

  private startAsyncPipelineReaction(): void {
    const dispose = reaction(
      () => ({
        query: this.search?.activeQuery ?? '',
        filterModel: this.filter?.model,
        sortKey: this.sort?.key,
        sortDir: this.sort?.dir ?? ('asc' as const),
        // Track raw item count so the reaction re-fires when source data changes.
        rawItemCount: this.rawItems.length,
      }),
      () => void this.runAsyncPipeline(),
      { fireImmediately: this.spec.source.kind !== 'async' }
    );
    this.disposers.push(dispose);
  }

  private async runAsyncPipeline(): Promise<void> {
    const token = ++this.pipelineToken;
    this.pipelineController?.abort();
    const controller = new AbortController();
    this.pipelineController = controller;
    runInAction(() => {
      this.status = 'loading';
      this.error = undefined;
    });
    try {
      const items = await runAsyncPipeline(
        this.spec,
        this.rawItems,
        {
          query: this.search?.activeQuery ?? '',
          filterModel: this.filter?.model as FilterModel | undefined,
          sortKey: this.sort?.key as string | undefined,
          sortDir: (this.sort?.dir ?? 'asc') as 'asc' | 'desc',
        },
        controller.signal
      );
      if (token !== this.pipelineToken || controller.signal.aborted) return;
      runInAction(() => {
        this._asyncPipelineItems = items;
        this.status = 'idle';
      });
    } catch (e) {
      if (token !== this.pipelineToken || controller.signal.aborted || isAbortError(e)) return;
      runInAction(() => {
        this.status = 'error';
        this.error = e;
      });
    } finally {
      if (this.pipelineController === controller) this.pipelineController = null;
    }
  }

  /** Stops all reactions and cancels in-flight requests. Called by `Root` on unmount. */
  dispose(): void {
    for (const d of this.disposers) d();
    this.disposers.length = 0;
    this.search?.dispose();
    this.pagination?.dispose();
    this.pipelineToken++;
    this.sourceToken++;
    this.pipelineController?.abort();
    this.pipelineController = null;
    this.sourceController?.abort();
    this.sourceController = null;
  }
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === 'AbortError';
}
