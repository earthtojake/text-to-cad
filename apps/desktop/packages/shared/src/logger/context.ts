import { noopLogger } from './noop';
import type { LogFields, Logger } from './types';

export type LogContextStore = {
  run<T>(logger: Logger, fn: () => T): T;
  get(): Logger | undefined;
};

class SyncLogContextStore implements LogContextStore {
  private current: Logger | undefined;

  run<T>(logger: Logger, fn: () => T): T {
    const previous = this.current;
    this.current = logger;
    try {
      return fn();
    } finally {
      this.current = previous;
    }
  }

  get(): Logger | undefined {
    return this.current;
  }
}

let rootLogger: Logger = noopLogger;
let contextStore: LogContextStore = new SyncLogContextStore();

export function setLogContextStore(store: LogContextStore): void {
  contextStore = store;
}

export function setRootLogger(logger: Logger): void {
  rootLogger = logger;
}

export function getCurrentLogger(): Logger {
  return contextStore.get() ?? rootLogger;
}

export function runWithLogger<T>(logger: Logger, fn: () => T): T {
  return contextStore.run(logger, fn);
}

export function withLogFields<T>(fields: LogFields, fn: () => T): T {
  return runWithLogger(getCurrentLogger().child(fields), fn);
}

export const log: Logger = {
  get level() {
    return getCurrentLogger().level;
  },
  debug(message, fields) {
    getCurrentLogger().debug(message, fields);
  },
  info(message, fields) {
    getCurrentLogger().info(message, fields);
  },
  warn(message, fields) {
    getCurrentLogger().warn(message, fields);
  },
  error(message, fields) {
    getCurrentLogger().error(message, fields);
  },
  child(bindings) {
    return getCurrentLogger().child(bindings);
  },
};
