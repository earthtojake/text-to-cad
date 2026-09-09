import { describe, expect, expectTypeOf, it, vi } from 'vitest';
import { compose, type Middleware } from './compose';

describe('compose', () => {
  it('returns the target when no middlewares are provided', () => {
    const handler = vi.fn((value: number) => value + 1);

    expect(compose(handler, [])).toBe(handler);
  });

  it('runs the first middleware as the outermost wrapper', () => {
    const events: string[] = [];
    const handler = (value: string) => {
      events.push('handler');
      return value.toUpperCase();
    };
    const outer: Middleware<typeof handler> = (next) => (value) => {
      events.push('outer:before');
      const result = next(value);
      events.push('outer:after');
      return result;
    };
    const inner: Middleware<typeof handler> = (next) => (value) => {
      events.push('inner:before');
      const result = next(value);
      events.push('inner:after');
      return result;
    };

    const composed = compose(handler, [outer, inner]);

    expect(composed('request')).toBe('REQUEST');
    expect(events).toEqual([
      'outer:before',
      'inner:before',
      'handler',
      'inner:after',
      'outer:after',
    ]);
  });

  it('does not mutate the middleware array', () => {
    const handler = (value: number) => value;
    const middleware: Middleware<typeof handler> = (next) => next;
    const middlewares = [middleware] as const;

    compose(handler, middlewares);

    expect(middlewares).toEqual([middleware]);
  });

  it('preserves function target types', () => {
    const handler = (input: { id: string }, _meta: { signal?: AbortSignal }) => input.id;
    const middleware: Middleware<typeof handler> = (next) => (input, meta) => next(input, meta);

    const composed = compose(handler, [middleware]);

    expectTypeOf(composed).toEqualTypeOf<typeof handler>();
    expect(composed({ id: 'same' }, {})).toBe('same');
  });

  it('works with object targets', async () => {
    type Target = {
      call(path: string, input: unknown): Promise<unknown>;
    };
    const target: Target = {
      call: vi.fn(async (_path, input) => input),
    };
    const middleware: Middleware<Target> = (next) => ({
      async call(path, input) {
        return await next.call(path, { wrapped: input });
      },
    });

    const composed = compose(target, [middleware]);

    await expect(composed.call('echo', 'value')).resolves.toEqual({ wrapped: 'value' });
    expect(target.call).toHaveBeenCalledWith('echo', { wrapped: 'value' });
  });
});
