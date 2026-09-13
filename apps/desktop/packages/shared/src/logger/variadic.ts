/**
 * Variadic compatibility adapter wrapping a strict Logger.
 * Converts the legacy (...input: unknown[]) call style to (message, fields).
 * Use at app entry points so existing call sites compile unchanged.
 */

import type { LogFields, LogLevel, Logger } from './types';

export function createVariadicAdapter(inner: Logger): VariadicLogger {
  function adapt(
    level: LogLevel,
    method: (msg: string, fields?: LogFields) => void,
    input: unknown[]
  ): void {
    if (input.length === 0) {
      method('');
      return;
    }

    const [first, ...rest] = input;

    if (
      typeof first === 'string' &&
      rest.length === 1 &&
      rest[0] !== null &&
      typeof rest[0] === 'object' &&
      !(rest[0] instanceof Error)
    ) {
      // Structured: log.info('message', { fields })
      method(first, rest[0] as LogFields);
    } else if (typeof first === 'string' && rest.length === 0) {
      method(first);
    } else {
      // Legacy variadic: log.error('msg:', error) or log.error('msg', error, more...)
      const message = typeof first === 'string' ? first : '';
      const extraFields = typeof first === 'string' ? rest : input;
      const fields =
        extraFields.length === 1
          ? { detail: extraFields[0] }
          : extraFields.length > 1
            ? { args: extraFields }
            : undefined;
      method(message, fields as LogFields | undefined);
    }
  }

  return {
    get level() {
      return inner.level;
    },
    debug: (...input: unknown[]) => adapt('debug', inner.debug.bind(inner), input),
    info: (...input: unknown[]) => adapt('info', inner.info.bind(inner), input),
    warn: (...input: unknown[]) => adapt('warn', inner.warn.bind(inner), input),
    error: (...input: unknown[]) => adapt('error', inner.error.bind(inner), input),
    child: (b: LogFields) => createVariadicAdapter(inner.child(b)),
  };
}

export type VariadicLogger = {
  readonly level: LogLevel;
  debug(...input: unknown[]): void;
  info(...input: unknown[]): void;
  warn(...input: unknown[]): void;
  error(...input: unknown[]): void;
  child(bindings: LogFields): VariadicLogger;
};
