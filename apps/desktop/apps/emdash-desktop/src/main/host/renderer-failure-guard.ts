export type RendererLoadFailure = {
  errorCode: number;
  errorDescription: string;
  validatedURL: string;
  isMainFrame: boolean;
};

export type RendererProcessFailure = {
  reason: string;
  exitCode: number;
};

export type RendererFailureGuard = {
  didFailLoad(failure: RendererLoadFailure): void;
  loadPromiseRejected(error: unknown): void;
  renderProcessGone(failure: RendererProcessFailure): void;
};

/**
 * Converts Electron renderer failures into one actionable startup error. A
 * navigation cancelled by a newer navigation is expected and is not a crash.
 */
export function createRendererFailureGuard(
  onFailure: (error: Error) => void
): RendererFailureGuard {
  let reported = false;
  const reportOnce = (error: Error): void => {
    if (reported) return;
    reported = true;
    onFailure(error);
  };

  return {
    didFailLoad(failure) {
      if (!failure.isMainFrame || failure.errorCode === -3) return;
      reportOnce(
        new Error(
          `The Hardcore interface could not load (${failure.errorDescription}, ` +
            `${failure.errorCode}) from ${failure.validatedURL || 'the app window'}.`
        )
      );
    },
    loadPromiseRejected(error) {
      reportOnce(
        error instanceof Error
          ? error
          : new Error(`The Hardcore interface could not load: ${String(error)}`)
      );
    },
    renderProcessGone(failure) {
      if (failure.reason === 'clean-exit') return;
      reportOnce(
        new Error(
          `The Hardcore interface stopped unexpectedly (${failure.reason}, exit ` +
            `${failure.exitCode}).`
        )
      );
    },
  };
}
