import { describe, expect, it } from 'vitest';
import { getCurrentLogger, log, runWithLogger, setRootLogger, withLogFields } from './context';
import { installAsyncLogContext } from './context-node';
import { noopLogger } from './noop';
import type { LogFields, LogLevel, Logger } from './types';

type LogCall = {
  level: LogLevel;
  message: string;
  fields?: LogFields;
};

function createStubLogger(
  bindings: LogFields = {},
  calls: LogCall[] = []
): {
  logger: Logger;
  calls: LogCall[];
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

describe('logger context', () => {
  it('uses the root logger outside a run context', () => {
    const { logger, calls } = createStubLogger();
    setRootLogger(logger);

    log.info('root', { ok: true });

    expect(calls).toEqual([{ level: 'info', message: 'root', fields: { ok: true } }]);
    setRootLogger(noopLogger);
  });

  it('uses a scoped logger while runWithLogger is active', () => {
    const root = createStubLogger();
    const scoped = createStubLogger();
    setRootLogger(root.logger);

    runWithLogger(scoped.logger, () => {
      log.debug('scoped');
    });
    log.debug('root');

    expect(scoped.calls).toEqual([{ level: 'debug', message: 'scoped', fields: undefined }]);
    expect(root.calls).toEqual([{ level: 'debug', message: 'root', fields: undefined }]);
    setRootLogger(noopLogger);
  });

  it('creates child context loggers with additional fields', () => {
    const { logger, calls } = createStubLogger({ service: 'wire' });

    runWithLogger(logger, () => {
      withLogFields({ callId: 'c1' }, () => {
        log.warn('slow call', { durationMs: 42 });
      });
    });

    expect(calls).toEqual([
      {
        level: 'warn',
        message: 'slow call',
        fields: { service: 'wire', callId: 'c1', durationMs: 42 },
      },
    ]);
  });

  it('preserves context across awaits when the node async store is installed', async () => {
    installAsyncLogContext();
    const { logger } = createStubLogger();

    await runWithLogger(logger, async () => {
      await Promise.resolve();
      expect(getCurrentLogger()).toBe(logger);
    });

    setRootLogger(noopLogger);
  });
});
