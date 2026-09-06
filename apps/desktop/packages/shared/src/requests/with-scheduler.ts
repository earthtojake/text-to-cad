import type { SignalContext, SignalHandler } from './handler';
import type { RequestScheduler } from './scheduler';

type Selector<I, C, T> = T | ((input: I, context: C) => T);

export type WithSchedulerOptions<I, C extends SignalContext> = {
  scheduler: RequestScheduler;
  priority: Selector<I, C, number>;
  cost?: Selector<I, C, number>;
  key?: (input: I, context: C) => string | undefined;
};

export function withScheduler<I, C extends SignalContext = SignalContext>(
  options: WithSchedulerOptions<I, C>
) {
  return function <O>(next: SignalHandler<I, O, C>): SignalHandler<I, O, C> {
    return (input, context) =>
      options.scheduler.submit(
        {
          priority: select(options.priority, input, context),
          cost: options.cost === undefined ? undefined : select(options.cost, input, context),
          key: options.key?.(input, context),
          run: async (signal) => await next(input, { ...context, signal } as C),
        },
        { signal: context.signal }
      );
  };
}

function select<I, C, T>(selector: Selector<I, C, T>, input: I, context: C): T {
  return typeof selector === 'function'
    ? (selector as (input: I, context: C) => T)(input, context)
    : selector;
}
