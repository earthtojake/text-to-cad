import { AsyncLocalStorage } from 'node:async_hooks';
import { setLogContextStore, type LogContextStore } from './context';
import type { Logger } from './types';

class AsyncLogContextStore implements LogContextStore {
  private readonly storage = new AsyncLocalStorage<Logger>();

  run<T>(logger: Logger, fn: () => T): T {
    return this.storage.run(logger, fn);
  }

  get(): Logger | undefined {
    return this.storage.getStore();
  }
}

export function installAsyncLogContext(): void {
  setLogContextStore(new AsyncLogContextStore());
}
