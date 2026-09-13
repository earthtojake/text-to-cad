import { action, makeObservable, observable } from 'mobx';
import type { SearchSpec } from '../types';

/**
 * SearchSlice — owns the query string with optional debouncing.
 *
 * `query`       — the raw input value; bind to the search input.
 * `activeQuery` — the debounced value that the pipeline reads for filtering.
 *
 * Sync search debounces to 0ms by default (immediate).
 * Async search defaults to 300ms.
 */
export class SearchSlice<T> {
  query = '';
  activeQuery = '';

  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor(readonly spec: SearchSpec<T>) {
    makeObservable(this, {
      query: observable,
      activeQuery: observable,
      setQuery: action,
      _flush: action,
    });
  }

  setQuery(q: string): void {
    this.query = q;
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    const ms = this.spec.debounceMs ?? (this.spec.kind === 'async' ? 300 : 0);
    if (ms === 0) {
      this.activeQuery = q;
    } else {
      this.timer = setTimeout(() => this._flush(q), ms);
    }
  }

  /** @internal Called by the debounce timer. */
  _flush(q: string): void {
    this.timer = null;
    this.activeQuery = q;
  }

  /** True while the debounce timer is still pending. */
  get isPending(): boolean {
    return this.query !== this.activeQuery;
  }

  dispose(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }
}
