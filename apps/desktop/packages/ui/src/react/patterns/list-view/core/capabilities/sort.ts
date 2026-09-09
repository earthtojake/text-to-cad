import { action, makeObservable, observable } from 'mobx';
import type { SortSpec } from '../types';

/**
 * SortSlice — observable sort key + direction.
 *
 * `key` and `dir` are tracked; components read them and actions mutate them.
 */
export class SortSlice<T, K extends string> {
  key: K;
  dir: 'asc' | 'desc';

  constructor(readonly spec: SortSpec<T, K>) {
    this.key = spec.initial.key;
    this.dir = spec.initial.dir;
    makeObservable(this, {
      key: observable,
      dir: observable,
      setKey: action,
      toggleDir: action,
      setDir: action,
    });
  }

  setKey(k: K): void {
    this.key = k;
  }

  setDir(d: 'asc' | 'desc'): void {
    this.dir = d;
  }

  toggleDir(): void {
    this.dir = this.dir === 'asc' ? 'desc' : 'asc';
  }
}
