import { describe, expect, it } from 'vitest';
import { z } from 'zod';
import {
  andThen,
  err,
  fail,
  gen,
  genAsync,
  isErr,
  isOk,
  map,
  mapErr,
  ok,
  orElse,
  Result,
  resultSchema,
  sequence,
  sequenceAll,
  tap,
  tapErr,
  toSerializedError,
  tryCatch,
  tryCatchAsync,
  unwrapGen,
  unwrapOr,
  unwrapOrElse,
  type Err,
} from './index';

// ---------------------------------------------------------------------------
// Constructors + guards
// ---------------------------------------------------------------------------

describe('ok / err / isOk / isErr', () => {
  it('ok produces a success result', () => {
    const r = ok(42);
    expect(r).toEqual({ success: true, data: 42 });
    expect(isOk(r)).toBe(true);
    expect(isErr(r)).toBe(false);
  });

  it('err produces a failure result', () => {
    const r = err('boom');
    expect(r).toEqual({ success: false, error: 'boom' });
    expect(isOk(r)).toBe(false);
    expect(isErr(r)).toBe(true);
  });

  it('ok with no argument defaults to undefined data', () => {
    const r = ok();
    expect(r.success).toBe(true);
    expect(r.data).toBeUndefined();
  });
});

describe('resultSchema', () => {
  const schema = resultSchema(z.object({ id: z.string() }), z.object({ type: z.string() }));

  it('parses success results', () => {
    expect(schema.parse({ success: true, data: { id: 'ok' } })).toEqual({
      success: true,
      data: { id: 'ok' },
    });
  });

  it('parses error results', () => {
    expect(schema.parse({ success: false, error: { type: 'failed' } })).toEqual({
      success: false,
      error: { type: 'failed' },
    });
  });
});

// ---------------------------------------------------------------------------
// fail + toSerializedError
// ---------------------------------------------------------------------------

describe('fail', () => {
  it('builds a tagged Err with message and typed cause', () => {
    const cause = toSerializedError(new Error('root'));
    const r = fail('network_error', { message: 'timeout', cause });
    expect(r.success).toBe(false);
    expect(r.error.type).toBe('network_error');
    expect(r.error.message).toBe('timeout');
    expect(r.error.cause?.name).toBe('Error');
    expect(r.error.cause?.message).toBe('root');
  });
});

describe('toSerializedError', () => {
  it('captures Error instances into a plain object', () => {
    const e = new TypeError('bad type');
    const s = toSerializedError(e);
    expect(s.name).toBe('TypeError');
    expect(s.message).toBe('bad type');
    expect(typeof s.stack).toBe('string');
  });

  it('handles non-Error thrown values', () => {
    const s = toSerializedError('string thrown');
    expect(s.name).toBe('Unknown');
    expect(s.message).toBe('string thrown');
  });

  it('produces a structuredClone-safe object', () => {
    const s = toSerializedError(new Error('cloneable'));
    const cloned = structuredClone(s);
    expect(cloned.name).toBe('Error');
    expect(cloned.message).toBe('cloneable');
  });

  it('keeps cloneable error data such as JSON-RPC details', () => {
    const e = Object.assign(new Error('Internal error'), {
      data: { details: 'Invalid value for config option model: claude-fable-5' },
    });
    const s = toSerializedError(e);
    expect(s.data).toEqual({ details: 'Invalid value for config option model: claude-fable-5' });
    expect(structuredClone(s).data).toEqual(s.data);
  });

  it('drops error data that cannot be cloned', () => {
    const e = Object.assign(new Error('boom'), {
      data: { fn: () => 1, cyc: {} as { self?: unknown } },
    });
    (e.data.cyc as { self?: unknown }).self = e.data.cyc;
    const s = toSerializedError(e);
    expect(s.data).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// Free-function combinators
// ---------------------------------------------------------------------------

describe('map', () => {
  it('transforms the success value', () => {
    expect(map(ok(2), (x) => x * 3)).toEqual(ok(6));
  });

  it('passes errors through unchanged', () => {
    const r = err('oops');
    expect(map(r, (x: number) => x * 2)).toBe(r);
  });
});

describe('mapErr', () => {
  it('transforms the error value', () => {
    expect(mapErr(err('oops'), (e) => e.toUpperCase())).toEqual(err('OOPS'));
  });

  it('passes success through unchanged', () => {
    const r = ok(42);
    expect(mapErr(r, () => 'new-error')).toBe(r);
  });
});

describe('andThen', () => {
  it('chains on success', () => {
    const r = andThen(ok(5), (x) => ok(x + 1));
    expect(r).toEqual(ok(6));
  });

  it('short-circuits on the first err', () => {
    const r = andThen(err('early'), (_x: number) => ok(99));
    expect(r).toEqual(err('early'));
  });

  it('propagates an inner err', () => {
    const r = andThen(ok(5), (_x) => err('inner'));
    expect(r).toEqual(err('inner'));
  });
});

describe('orElse', () => {
  it('passes through success', () => {
    const r = ok(1);
    expect(orElse(r, () => ok(2))).toBe(r);
  });

  it('recovers from error', () => {
    expect(orElse(err('e'), () => ok(42))).toEqual(ok(42));
  });
});

describe('unwrapOr / unwrapOrElse', () => {
  it('unwrapOr returns data on success', () => {
    expect(unwrapOr(ok(7), 0)).toBe(7);
  });

  it('unwrapOr returns fallback on err', () => {
    expect(unwrapOr(err('e'), 99)).toBe(99);
  });

  it('unwrapOrElse computes fallback from error', () => {
    expect(unwrapOrElse(err('bang'), (e) => e.length)).toBe(4);
  });
});

describe('tap / tapErr', () => {
  it('tap runs side effect on success and returns same result', () => {
    let seen: number | undefined;
    const r = ok(10);
    const out = tap(r, (x) => {
      seen = x;
    });
    expect(seen).toBe(10);
    expect(out).toBe(r);
  });

  it('tap is a no-op on err', () => {
    let called = false;
    const r = err('e');
    tap(r, () => {
      called = true;
    });
    expect(called).toBe(false);
  });

  it('tapErr runs on error', () => {
    let seen: string | undefined;
    tapErr(err('boom'), (e) => {
      seen = e;
    });
    expect(seen).toBe('boom');
  });
});

// ---------------------------------------------------------------------------
// sequence / sequenceAll
// ---------------------------------------------------------------------------

describe('sequence', () => {
  it('returns all data when all succeed', () => {
    expect(sequence([ok(1), ok(2), ok(3)])).toEqual(ok([1, 2, 3]));
  });

  it('returns the first err', () => {
    const first = err('first');
    const result = sequence([ok(1), first, err('second')]);
    expect(result).toEqual(first);
  });

  it('handles empty array', () => {
    expect(sequence([])).toEqual(ok([]));
  });
});

describe('sequenceAll', () => {
  it('returns all data when all succeed', () => {
    expect(sequenceAll([ok(1), ok(2)])).toEqual(ok([1, 2]));
  });

  it('collects all errors', () => {
    const result = sequenceAll([ok(1), err('a'), ok(2), err('b')]);
    expect(result).toEqual(err(['a', 'b']));
  });
});

// ---------------------------------------------------------------------------
// tryCatch / tryCatchAsync
// ---------------------------------------------------------------------------

describe('tryCatch', () => {
  it('wraps a successful function', () => {
    expect(tryCatch(() => 42)).toEqual(ok(42));
  });

  it('wraps a throwing function into a SerializedError', () => {
    const r = tryCatch(() => {
      throw new Error('oops');
    });
    expect(isErr(r)).toBe(true);
    if (isErr(r)) {
      expect(r.error.name).toBe('Error');
      expect(r.error.message).toBe('oops');
    }
  });

  it('accepts a custom onError mapper', () => {
    const r = tryCatch(
      () => {
        throw 'raw';
      },
      (e) => ({ type: 'custom' as const, raw: e })
    );
    expect(r).toEqual(err({ type: 'custom', raw: 'raw' }));
  });
});

describe('tryCatchAsync', () => {
  it('wraps a resolved promise', async () => {
    expect(await tryCatchAsync(async () => 'hi')).toEqual(ok('hi'));
  });

  it('wraps a rejected promise', async () => {
    const r = await tryCatchAsync(async () => {
      throw new Error('async oops');
    });
    expect(isErr(r)).toBe(true);
    if (isErr(r)) {
      expect(r.error.message).toBe('async oops');
    }
  });
});

// ---------------------------------------------------------------------------
// Generator do-notation
// ---------------------------------------------------------------------------

describe('gen / unwrapGen', () => {
  it('threads success values through the generator', () => {
    // eslint-disable-next-line require-yield
    const r = gen(function* (): Generator<Err<string>, number, any> {
      const a = yield* unwrapGen(ok(2));
      const b = yield* unwrapGen(ok(3));
      return a + b;
    });
    expect(r).toEqual(ok(5));
  });

  it('short-circuits on the first err', () => {
    const r = gen(function* (): Generator<Err<string>, number, any> {
      yield* unwrapGen(err('stop'));
      yield* unwrapGen(ok(99));
      return 42;
    });
    expect(r).toEqual(err('stop'));
  });
});

describe('genAsync', () => {
  it('threads async success values', async () => {
    const r = await genAsync(async function* (): AsyncGenerator<Err<string>, number, any> {
      const a = yield* unwrapGen(ok(10));
      return a * 2;
    });
    expect(r).toEqual(ok(20));
  });

  it('short-circuits on async err', async () => {
    const r = await genAsync(async function* (): AsyncGenerator<Err<string>, number, any> {
      yield* unwrapGen(err('async-stop'));
      return 999;
    });
    expect(r).toEqual(err('async-stop'));
  });
});

// ---------------------------------------------------------------------------
// Fluent API — Result.from / Result.fromAsync
// ---------------------------------------------------------------------------

describe('Result.from', () => {
  it('chains map + mapErr and unwraps to a plain Result', () => {
    const r = Result.from(ok(5))
      .map((x) => x * 2)
      .unwrap();
    expect(r).toEqual(ok(10));
  });

  it('mapErr on success is a no-op', () => {
    const r = Result.from(ok(5))
      .mapErr(() => 'new-error')
      .unwrap();
    expect(r).toEqual(ok(5));
  });

  it('chains andThen', () => {
    const r = Result.from(ok(3))
      .andThen((x) => ok(x + 1))
      .map((x) => x * 10)
      .unwrap();
    expect(r).toEqual(ok(40));
  });

  it('toJSON returns the plain Result', () => {
    const plain = ok(42);
    expect(Result.from(plain).toJSON()).toEqual(plain);
  });

  it('unwrapOr on err returns fallback', () => {
    expect(Result.from(err('e')).unwrapOr(99)).toBe(99);
  });
});

describe('Result.fromAsync', () => {
  it('awaits to a plain Result', async () => {
    const r = await Result.fromAsync(Promise.resolve(ok(7)));
    expect(r).toEqual(ok(7));
  });

  it('chains map across an async result', async () => {
    const r = await Result.fromAsync(Promise.resolve(ok(3))).map((x) => x * 4);
    expect(r).toEqual(ok(12));
  });

  it('chains mapErr on an async err', async () => {
    const r = await Result.fromAsync(Promise.resolve(err('oops'))).mapErr((e: string) =>
      e.toUpperCase()
    );
    expect(r).toEqual(err('OOPS'));
  });

  it('chains andThen async step', async () => {
    const r = await Result.fromAsync(Promise.resolve(ok(2))).andThen(async (x) => ok(x + 8));
    expect(r).toEqual(ok(10));
  });

  it('tap runs side effect without changing result', async () => {
    let seen: number | undefined;
    const r = await Result.fromAsync(Promise.resolve(ok(5))).tap((x) => {
      seen = x;
    });
    expect(seen).toBe(5);
    expect(r).toEqual(ok(5));
  });
});

describe('Result.try / Result.tryAsync', () => {
  it('wraps a non-throwing function', () => {
    expect(Result.try(() => 42)).toEqual(ok(42));
  });

  it('wraps an async non-throwing function', async () => {
    expect(await Result.tryAsync(async () => 42)).toEqual(ok(42));
  });
});

// ---------------------------------------------------------------------------
// IPC serializability — cause chain survives structuredClone
// ---------------------------------------------------------------------------

describe('IPC serializability', () => {
  it('a plain ok/err result survives structuredClone', () => {
    const r = ok({ value: 42 });
    expect(structuredClone(r)).toEqual(r);

    const e = err({ type: 'network_error', message: 'timeout' });
    expect(structuredClone(e)).toEqual(e);
  });

  it('a cause chain with SerializedError survives structuredClone', () => {
    const inner = toSerializedError(new Error('root cause'));
    const r = fail('outer_error', { message: 'outer', cause: inner });
    const cloned = structuredClone(r);
    expect(cloned.error.cause?.message).toBe('root cause');
    expect(cloned.error.cause?.name).toBe('Error');
  });

  it('a BaseError cause chain survives structuredClone', () => {
    const inner = fail('inner_error', { message: 'inner' });
    const outer = fail('outer_error', { message: 'outer', cause: inner.error });
    const cloned = structuredClone(outer);
    expect(cloned.error.cause?.type).toBe('inner_error');
    expect(cloned.error.cause?.message).toBe('inner');
  });

  it('JSON.stringify round-trips a result with cause', () => {
    const cause = toSerializedError(new Error('json-root'));
    const r = fail('json_error', { message: 'outer', cause });
    const parsed = JSON.parse(JSON.stringify(r)) as typeof r;
    expect(parsed.error.cause?.message).toBe('json-root');
  });
});
