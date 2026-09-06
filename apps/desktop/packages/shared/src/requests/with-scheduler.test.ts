import { describe, expect, it } from 'vitest';
import { createScope } from '../concurrency';
import { compose } from './compose';
import { createRequestScheduler } from './scheduler';
import { withScheduler } from './with-scheduler';

describe('withScheduler', () => {
  it('preserves context and schedules selected request metadata', async () => {
    const scope = createScope({ label: 'scheduler-middleware-test' });
    const scheduler = createRequestScheduler({ scope, maxConcurrency: 1 });
    const handler = async (
      input: { id: string; priority: number },
      context: { signal?: AbortSignal; traceId: string }
    ) => {
      expect(context.traceId).toBe('trace');
      expect(context.signal).toBeInstanceOf(AbortSignal);
      return input.id;
    };
    const scheduled = compose(handler, [
      withScheduler<{ id: string; priority: number }, { signal?: AbortSignal; traceId: string }>({
        scheduler,
        priority: (input) => input.priority,
        cost: 1,
        key: (input) => input.id,
      }),
    ]);

    await expect(scheduled({ id: 'same', priority: 2 }, { traceId: 'trace' })).resolves.toBe(
      'same'
    );
    await scheduler.dispose();
    await scope.dispose();
  });
});
