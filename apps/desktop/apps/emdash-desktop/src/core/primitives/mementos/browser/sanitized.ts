import type { Scope } from '@emdash/shared/concurrency';
import { computed, makeObservable, type IReactionDisposer } from 'mobx';
import type { MementoHandle } from './memento-client';

export interface SanitizedMementoOptions<TValue, TDependencies> {
  /**
   * Return undefined while domain data is not loaded. Sanitization is skipped
   * in that state so loading cannot be mistaken for entity deletion.
   */
  readonly deps: () => TDependencies | undefined;
  readonly sanitize: (value: TValue, dependencies: TDependencies) => TValue;
}

export function sanitizedMemento<TValue, TDependencies>(
  handle: MementoHandle<TValue>,
  options: SanitizedMementoOptions<TValue, TDependencies>
): MementoHandle<TValue> {
  return new SanitizedMementoHandle(handle, options);
}

class SanitizedMementoHandle<TValue, TDependencies> implements MementoHandle<TValue> {
  constructor(
    private readonly handle: MementoHandle<TValue>,
    private readonly options: SanitizedMementoOptions<TValue, TDependencies>
  ) {
    makeObservable(this, { value: computed.struct });
  }

  get value(): TValue {
    const value = this.handle.value;
    const dependencies = this.options.deps();
    return dependencies === undefined ? value : this.options.sanitize(value, dependencies);
  }

  get ready(): Promise<void> {
    return this.handle.ready;
  }

  get isPending(): boolean {
    return this.handle.isPending;
  }

  get hasStoredValue(): boolean {
    return this.handle.hasStoredValue;
  }

  read(): TValue {
    return this.value;
  }

  update(next: TValue | ((current: TValue) => TValue)): void {
    this.handle.update(next);
  }

  reset(): Promise<void> {
    return this.handle.reset();
  }

  flush(): Promise<void> {
    return this.handle.flush();
  }

  autoPersist(read: () => TValue, scope?: Scope): IReactionDisposer {
    return this.handle.autoPersist(read, scope);
  }

  dispose(): Promise<void> {
    return this.handle.dispose();
  }
}
