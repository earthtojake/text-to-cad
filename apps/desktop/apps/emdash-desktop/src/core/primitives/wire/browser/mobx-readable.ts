import type { Scope } from '@emdash/shared/concurrency';
import { observe, type Readable, type Snapshot } from '@emdash/wire/state';
import { runInAction } from 'mobx';

export function observeReadableInAction<T>(
  source: Readable<T>,
  listener: (snapshot: Snapshot<T>) => void,
  options: { scope: Scope; immediate?: boolean }
): void {
  observe(
    source,
    (current) => {
      runInAction(() => listener(current));
    },
    options
  );
}
