import { action, makeObservable, observable } from 'mobx';
import type { FilterModel, FilterSpec } from '../types';

/**
 * FilterSlice — observable filter model with `set` / `reset` actions.
 *
 * `model` is the current filter state; it's tracked by MobX so any
 * `computed` or `reaction` that reads it will rerun when it changes.
 */
export class FilterSlice<T, F extends FilterModel> {
  model: F;

  constructor(readonly spec: FilterSpec<T, F>) {
    this.model = { ...spec.initial };
    makeObservable(this, {
      model: observable,
      set: action,
      reset: action,
    });
  }

  set(patch: Partial<F>): void {
    Object.assign(this.model, patch);
  }

  reset(): void {
    Object.assign(this.model, this.spec.initial);
  }
}
