import { z } from 'zod';

// ---------------------------------------------------------------------------
// Serializability primitives
// ---------------------------------------------------------------------------

/** A value guaranteed to survive structuredClone / JSON across the IPC boundary. */
export type Serializable =
  | string
  | number
  | boolean
  | null
  | { readonly [key: string]: Serializable }
  | readonly Serializable[];

/** The serializable shadow of a thrown JS Error, captured at a catch boundary. */
export type SerializedError = {
  readonly name: string;
  readonly message: string;
  readonly stack?: string;
  /** Structured detail carried by the error (for example JSON-RPC error data), when cloneable. */
  readonly data?: unknown;
};

/** Normalizes any thrown value into a cloneable SerializedError. */
export const toSerializedError = (e: unknown): SerializedError => {
  if (!(e instanceof Error)) return { name: 'Unknown', message: String(e) };
  const data = cloneableErrorData((e as { data?: unknown }).data);
  return {
    name: e.name,
    message: e.message,
    stack: e.stack,
    ...(data !== undefined ? { data } : {}),
  };
};

/** JSON-RPC style errors carry their real reason in `data`; keep it only when it survives cloning. */
function cloneableErrorData(value: unknown): unknown {
  if (value === undefined || value === null) return undefined;
  try {
    return JSON.parse(JSON.stringify(value)) as unknown;
  } catch {
    return undefined;
  }
}

// ---------------------------------------------------------------------------
// Core Result shape — plain objects, never class instances, safe on the wire
// ---------------------------------------------------------------------------

export type Ok<T> = { readonly success: true; readonly data: T };
export type Err<E> = { readonly success: false; readonly error: E };
export type Result<T, E = string> = Ok<T> | Err<E>;

export const ok = <T>(data: T = undefined as T): Ok<T> => ({ success: true, data });
export const err = <E>(error: E): Err<E> => ({ success: false, error });

/**
 * Wraps a Result<T, E> on the wire as a discriminated union.
 * Domain outcomes use this helper; transport-level failures should stay in
 * the transport's error mechanism.
 */
export const resultSchema = <D extends z.ZodTypeAny, E extends z.ZodTypeAny>(data: D, error: E) =>
  z.discriminatedUnion('success', [
    z.object({ success: z.literal(true), data }),
    z.object({ success: z.literal(false), error }),
  ]);

// ---------------------------------------------------------------------------
// Tagged errors with a typed, serializable cause chain
// ---------------------------------------------------------------------------

/**
 * A discriminated error with an optional, recursively-typed cause.
 * `Cause` must be another `BaseError` or a `SerializedError` so the whole
 * chain stays structuredClone-safe across the IPC boundary.
 */
export type BaseError<
  Type extends string = string,
  Cause extends BaseError | SerializedError | undefined = undefined,
> = {
  readonly type: Type;
  readonly message?: string;
  readonly cause?: Cause;
};

/**
 * Builds a tagged `Err` with an optional typed cause in one call.
 *
 * @example
 * return fail('session_persistence_failed', {
 *   message: 'Failed to retrieve token',
 *   cause: toSerializedError(error),
 * });
 */
export const fail = <
  Type extends string,
  Cause extends BaseError | SerializedError | undefined = undefined,
>(
  type: Type,
  opts?: { message?: string; cause?: Cause }
): Err<BaseError<Type, Cause>> =>
  err({ type, message: opts?.message, cause: opts?.cause } as BaseError<Type, Cause>);

// ---------------------------------------------------------------------------
// Guards
// ---------------------------------------------------------------------------

export const isOk = <T, E>(r: Result<T, E>): r is Ok<T> => r.success;
export const isErr = <T, E>(r: Result<T, E>): r is Err<E> => !r.success;

// ---------------------------------------------------------------------------
// Inference helpers — derive the data / error type from a Result, a
// Promise<Result>, or a function returning either. Single source of truth.
// ---------------------------------------------------------------------------

// oxlint-disable-next-line typescript/no-explicit-any
export type DataOf<R> = R extends (...args: any[]) => infer Ret
  ? DataOf<Ret>
  : R extends Promise<infer V>
    ? DataOf<V>
    : R extends Ok<infer T>
      ? T
      : never;

// oxlint-disable-next-line typescript/no-explicit-any
export type ErrorOf<R> = R extends (...args: any[]) => infer Ret
  ? ErrorOf<Ret>
  : R extends Promise<infer V>
    ? ErrorOf<V>
    : R extends Err<infer E>
      ? E
      : never;

// ---------------------------------------------------------------------------
// Free-function combinators — operate on plain objects, identical before and
// after IPC, no wrapper overhead.
// ---------------------------------------------------------------------------

/** Transform the success value; errors pass through unchanged. */
export const map = <T, U, E>(r: Result<T, E>, f: (v: T) => U): Result<U, E> =>
  r.success ? ok(f(r.data)) : r;

/** Transform the error value; success passes through unchanged. */
export const mapErr = <T, E, F>(r: Result<T, E>, f: (e: E) => F): Result<T, F> =>
  r.success ? r : err(f(r.error));

/** Chain a fallible sync operation. Short-circuits on the first Err. */
export const andThen = <T, U, E, F>(r: Result<T, E>, f: (v: T) => Result<U, F>): Result<U, E | F> =>
  r.success ? f(r.data) : r;

/** Chain a fallible async operation. Short-circuits on the first Err. */
export const andThenAsync = async <T, U, E, F>(
  r: Result<T, E>,
  f: (v: T) => Promise<Result<U, F>>
): Promise<Result<U, E | F>> => (r.success ? f(r.data) : r);

/** Recover from an error by providing an alternative Result. */
export const orElse = <T, E, F>(r: Result<T, E>, f: (e: E) => Result<T, F>): Result<T, F> =>
  r.success ? r : f(r.error);

/** Unwrap the success value or return a fallback. */
export const unwrapOr = <T, E>(r: Result<T, E>, fallback: T): T => (r.success ? r.data : fallback);

/** Unwrap the success value or compute a fallback from the error. */
export const unwrapOrElse = <T, E>(r: Result<T, E>, f: (e: E) => T): T =>
  r.success ? r.data : f(r.error);

/** Run a side-effect on success without altering the Result. */
export const tap = <T, E>(r: Result<T, E>, f: (v: T) => void): Result<T, E> => {
  if (r.success) f(r.data);
  return r;
};

/** Run a side-effect on failure without altering the Result. */
export const tapErr = <T, E>(r: Result<T, E>, f: (e: E) => void): Result<T, E> => {
  if (!r.success) f(r.error);
  return r;
};

// ---------------------------------------------------------------------------
// Aggregation
// ---------------------------------------------------------------------------

/** Fail-fast: returns the first Err encountered, otherwise all data as an array. */
export const sequence = <T, E>(results: readonly Result<T, E>[]): Result<T[], E> => {
  const data: T[] = [];
  for (const r of results) {
    if (!r.success) return r;
    data.push(r.data);
  }
  return ok(data);
};

/** Collect-all: gathers every error instead of stopping at the first. */
export const sequenceAll = <T, E>(results: readonly Result<T, E>[]): Result<T[], E[]> => {
  const data: T[] = [];
  const errors: E[] = [];
  for (const r of results) {
    if (r.success) data.push(r.data);
    else errors.push(r.error);
  }
  return errors.length > 0 ? err(errors) : ok(data);
};

// ---------------------------------------------------------------------------
// Wrapping throwing / promise-returning code into a Result
// ---------------------------------------------------------------------------

export const tryCatch = <T, E = SerializedError>(
  fn: () => T,
  onError: (e: unknown) => E = toSerializedError as (e: unknown) => E
): Result<T, E> => {
  try {
    return ok(fn());
  } catch (e) {
    return err(onError(e));
  }
};

export const tryCatchAsync = async <T, E = SerializedError>(
  fn: () => Promise<T>,
  onError: (e: unknown) => E = toSerializedError as (e: unknown) => E
): Promise<Result<T, E>> => {
  try {
    return ok(await fn());
  } catch (e) {
    return err(onError(e));
  }
};

// ---------------------------------------------------------------------------
// Generator do-notation — write happy-path code that auto-short-circuits.
//
// Usage:
//   const result = gen(function* () {
//     const a = yield* unwrapGen(stepOne());
//     const b = yield* unwrapGen(stepTwo(a));
//     return { a, b };
//   });
// ---------------------------------------------------------------------------

// oxlint-disable-next-line typescript/no-explicit-any
export function* unwrapGen<T, E>(r: Result<T, E>): Generator<Err<E>, T, any> {
  if (r.success) return r.data;
  yield r;
  // Unreachable: the generator is never resumed after yielding an Err.
  throw new Error('unreachable');
}

// oxlint-disable-next-line typescript/no-explicit-any
export function gen<T, E>(body: () => Generator<Err<E>, T, any>): Result<T, E> {
  const it = body();
  const step = it.next();
  return step.done ? ok(step.value) : step.value;
}

export async function* unwrapGenAsync<T, E>(
  r: Result<T, E> | Promise<Result<T, E>>
  // oxlint-disable-next-line typescript/no-explicit-any
): AsyncGenerator<Err<E>, T, any> {
  const awaited = await r;
  if (awaited.success) return awaited.data;
  yield awaited;
  throw new Error('unreachable');
}

export async function genAsync<T, E>(
  body: () => AsyncGenerator<Err<E>, T, any> // oxlint-disable-line typescript/no-explicit-any
): Promise<Result<T, E>> {
  const it = body();
  const step = await it.next();
  return step.done ? ok(step.value) : step.value;
}

// ---------------------------------------------------------------------------
// Opt-in fluent wrappers — local chaining sugar; never appear in wire/return
// types. FluentResult wraps sync Results; AsyncResult wraps Promises of Results
// and is itself PromiseLike so `await` resolves to a plain Result.
// ---------------------------------------------------------------------------

class FluentResult<T, E> {
  constructor(private readonly r: Result<T, E>) {}

  map<U>(f: (v: T) => U): FluentResult<U, E> {
    return new FluentResult(map(this.r, f));
  }

  mapErr<F>(f: (e: E) => F): FluentResult<T, F> {
    return new FluentResult(mapErr(this.r, f));
  }

  andThen<U, F>(f: (v: T) => Result<U, F>): FluentResult<U, E | F> {
    return new FluentResult(andThen(this.r, f));
  }

  orElse<F>(f: (e: E) => Result<T, F>): FluentResult<T, F> {
    return new FluentResult(orElse(this.r, f));
  }

  tap(f: (v: T) => void): FluentResult<T, E> {
    return new FluentResult(tap(this.r, f));
  }

  tapErr(f: (e: E) => void): FluentResult<T, E> {
    return new FluentResult(tapErr(this.r, f));
  }

  unwrapOr(fallback: T): T {
    return unwrapOr(this.r, fallback);
  }

  /** Exit the fluent wrapper and return the plain, serializable Result. */
  unwrap(): Result<T, E> {
    return this.r;
  }

  toJSON(): Result<T, E> {
    return this.r;
  }
}

class AsyncResult<T, E> implements PromiseLike<Result<T, E>> {
  constructor(private readonly p: Promise<Result<T, E>>) {}

  map<U>(f: (v: T) => U | Promise<U>): AsyncResult<U, E> {
    return new AsyncResult(this.p.then(async (r) => (r.success ? ok(await f(r.data)) : r)));
  }

  mapErr<F>(f: (e: E) => F): AsyncResult<T, F> {
    return new AsyncResult(this.p.then((r) => mapErr(r, f)));
  }

  andThen<U, F>(f: (v: T) => Result<U, F> | Promise<Result<U, F>>): AsyncResult<U, E | F> {
    return new AsyncResult<U, E | F>(
      this.p.then(async (r): Promise<Result<U, E | F>> => (r.success ? f(r.data) : r))
    );
  }

  orElse<F>(f: (e: E) => Result<T, F> | Promise<Result<T, F>>): AsyncResult<T, F> {
    return new AsyncResult<T, F>(
      this.p.then(async (r): Promise<Result<T, F>> => (r.success ? r : f(r.error)))
    );
  }

  tap(f: (v: T) => void): AsyncResult<T, E> {
    return new AsyncResult(this.p.then((r) => tap(r, f)));
  }

  tapErr(f: (e: E) => void): AsyncResult<T, E> {
    return new AsyncResult(this.p.then((r) => tapErr(r, f)));
  }

  unwrapOr(fallback: T): Promise<T> {
    return this.p.then((r) => unwrapOr(r, fallback));
  }

  unwrapOrElse(f: (e: E) => T | Promise<T>): Promise<T> {
    return this.p.then((r) => (r.success ? r.data : f(r.error)));
  }

  /**
   * PromiseLike implementation: `await asyncResult` resolves to a plain Result,
   * ready for use on either side of the IPC boundary.
   */
  then<R1 = Result<T, E>, R2 = never>(
    onfulfilled?: ((v: Result<T, E>) => R1 | PromiseLike<R1>) | null,
    onrejected?: ((reason: unknown) => R2 | PromiseLike<R2>) | null
  ): PromiseLike<R1 | R2> {
    return this.p.then(onfulfilled, onrejected);
  }
}

/**
 * Entry points for the opt-in fluent API.
 *
 * @example
 * // Sync chain
 * const r = Result.from(someResult).map(transform).mapErr(retag).unwrap();
 *
 * // Async chain — awaits to a plain Result
 * const r = await Result.fromAsync(somePromise).map(transform).mapErr(retag);
 *
 * // Wrapping a throwing function
 * const r = Result.try(() => JSON.parse(input));
 * const r = await Result.tryAsync(() => fetch(url).then((res) => res.json()));
 */
export const Result = {
  from: <T, E>(r: Result<T, E>): FluentResult<T, E> => new FluentResult(r),
  fromAsync: <T, E>(p: Promise<Result<T, E>>): AsyncResult<T, E> => new AsyncResult(p),
  try: tryCatch,
  tryAsync: <T>(fn: () => Promise<T>): AsyncResult<T, SerializedError> =>
    new AsyncResult(tryCatchAsync(fn)),
};
