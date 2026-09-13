export type SignalContext = {
  signal?: AbortSignal;
};

export type SignalHandler<I, O, C extends SignalContext = SignalContext> = (
  input: I,
  context: C
) => Promise<O>;
