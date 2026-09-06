// Result is exported as a value (which also carries the type for type-position usage).
// All other result types use inline 'type' to keep them type-only.
export {
  andThen,
  andThenAsync,
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
  unwrapGenAsync,
  unwrapOr,
  unwrapOrElse,
  type BaseError,
  type DataOf,
  type Err,
  type ErrorOf,
  type Ok,
  type Serializable,
  type SerializedError,
} from './result/index';
export { Secret, secret, isSecret, reveal, REDACTED } from './secret';
export {
  createEmitter,
  type Emitter,
  type EmitterOptions,
  type EmitterSubscriberError,
} from './emitter';
export { isDeepEqual } from './deep-equal';
export { once, toPendingLease } from './lifecycle';
export type { PendingLease, Lease, Unsubscribe } from './lifecycle';
