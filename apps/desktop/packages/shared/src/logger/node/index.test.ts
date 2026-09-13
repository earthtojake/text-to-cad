import { describe, expect, it } from 'vitest';
import { getCurrentLogger, log, runWithLogger, setRootLogger } from '../context';
import { noopLogger } from '../noop';
import { initProcessLogging } from './index';

describe('initProcessLogging', () => {
  it('sets the process logger as the ambient root logger', async () => {
    const writes: string[] = [];
    const destination = {
      write(line: string) {
        writes.push(line);
        return true;
      },
    };

    const logger = initProcessLogging({
      name: 'test-runtime',
      env: { EMDASH_LOG_LEVEL: 'debug' },
      destination,
    });

    expect(getCurrentLogger()).toBe(logger);

    log.info('ready', { runtimeId: 'r1' });
    await runWithLogger(logger.child({ scope: 'child' }), async () => {
      await Promise.resolve();
      log.debug('scoped');
    });

    expect(writes.map((line) => JSON.parse(line))).toEqual([
      expect.objectContaining({
        level: 'info',
        msg: 'ready',
        proc: 'test-runtime',
        runtimeId: 'r1',
      }),
      expect.objectContaining({
        level: 'debug',
        msg: 'scoped',
        proc: 'test-runtime',
        scope: 'child',
      }),
    ]);

    setRootLogger(noopLogger);
  });
});
