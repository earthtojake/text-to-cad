export type RendererBootGate = {
  readonly signal: AbortSignal;
  fail(error: Error): void;
  loaded(): void;
  waitForBackend(backend: Promise<void>): Promise<void>;
};

/**
 * Keeps bootstrap pending until the backend and renderer have both completed.
 * A renderer failure also aborts the backend chain so it stops publishing new
 * services while the app transitions to recovery.
 */
export function createRendererBootGate(): RendererBootGate {
  const controller = new AbortController();
  let resolveLoaded!: () => void;
  let resolveFailure!: (error: Error) => void;
  const rendererLoaded = new Promise<void>((resolve) => {
    resolveLoaded = resolve;
  });
  const rendererFailure = new Promise<Error>((resolve) => {
    resolveFailure = resolve;
  });

  return {
    signal: controller.signal,
    fail(error) {
      if (controller.signal.aborted) return;
      controller.abort(error);
      resolveFailure(error);
    },
    loaded() {
      resolveLoaded();
    },
    waitForBackend(backend) {
      return Promise.race([
        Promise.all([backend, rendererLoaded]).then(() => undefined),
        rendererFailure.then((error) => Promise.reject(error)),
      ]);
    },
  };
}
