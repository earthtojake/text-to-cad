import { runWithTimeout, type Clock } from '../scheduling';
import type { SignalContext, SignalHandler } from './handler';

export type WithTimeoutOptions = {
  timeoutMs: number;
  clock?: Clock;
};

export function withTimeout(options: WithTimeoutOptions) {
  return function <I, O, C extends SignalContext>(
    next: SignalHandler<I, O, C>
  ): SignalHandler<I, O, C> {
    return (input, context) =>
      runWithTimeout((signal) => next(input, { ...context, signal } as C), {
        timeoutMs: options.timeoutMs,
        signal: context.signal,
        clock: options.clock,
      });
  };
}
