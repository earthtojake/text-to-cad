import { resultSchema } from '@emdash/shared';

/**
 * Wraps a Result<T,E> on the wire as a discriminated union.
 * Domain outcomes use this helper; transport-level failures use oRPC .errors().
 */
export const result = resultSchema;
