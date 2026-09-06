import type { Logger } from './types';

/**
 * No-op Logger for tests or contexts without a log sink.
 * Discards every call and returns itself from child() so bindings are ignored.
 */
export const noopLogger: Logger = {
  level: 'error',
  debug: () => {},
  info: () => {},
  warn: () => {},
  error: () => {},
  child: () => noopLogger,
};
