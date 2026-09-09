import type { LogFields, Logger, LogLevel } from '@emdash/shared/logger';

export type StubLogCall = {
  level: LogLevel;
  message: string;
  fields?: LogFields;
};

export function createStubLogger(
  bindings: LogFields = {},
  calls: StubLogCall[] = []
): {
  logger: Logger;
  calls: StubLogCall[];
} {
  const logger: Logger = {
    level: 'debug',
    debug: (message, fields) => calls.push({ level: 'debug', message, fields: merge(fields) }),
    info: (message, fields) => calls.push({ level: 'info', message, fields: merge(fields) }),
    warn: (message, fields) => calls.push({ level: 'warn', message, fields: merge(fields) }),
    error: (message, fields) => calls.push({ level: 'error', message, fields: merge(fields) }),
    child: (childBindings) => createStubLogger({ ...bindings, ...childBindings }, calls).logger,
  };

  function merge(fields: LogFields | undefined): LogFields | undefined {
    const merged = { ...bindings, ...fields };
    return Object.keys(merged).length > 0 ? merged : undefined;
  }

  return { logger, calls };
}
