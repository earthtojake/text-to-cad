import { describe, expect, it, vi } from 'vitest';
import { createRendererFailureGuard } from './renderer-failure-guard';

describe('renderer failure guard', () => {
  it('reports a failed main-frame load once', () => {
    const onFailure = vi.fn();
    const guard = createRendererFailureGuard(onFailure);

    guard.didFailLoad({
      errorCode: -102,
      errorDescription: 'ERR_CONNECTION_REFUSED',
      validatedURL: 'http://localhost:3000/',
      isMainFrame: true,
    });
    guard.renderProcessGone({ reason: 'crashed', exitCode: 1 });

    expect(onFailure).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ message: expect.stringContaining('ERR_CONNECTION_REFUSED') })
    );
  });

  it('ignores subframes, superseded navigations, and clean renderer exits', () => {
    const onFailure = vi.fn();
    const guard = createRendererFailureGuard(onFailure);

    guard.didFailLoad({
      errorCode: -102,
      errorDescription: 'ERR_CONNECTION_REFUSED',
      validatedURL: 'https://example.com/',
      isMainFrame: false,
    });
    guard.didFailLoad({
      errorCode: -3,
      errorDescription: 'ERR_ABORTED',
      validatedURL: 'http://localhost:3000/',
      isMainFrame: true,
    });
    guard.renderProcessGone({ reason: 'clean-exit', exitCode: 0 });

    expect(onFailure).not.toHaveBeenCalled();
  });

  it('routes a rejected load promise through the same one-shot failure path', () => {
    const onFailure = vi.fn();
    const guard = createRendererFailureGuard(onFailure);

    guard.loadPromiseRejected(new Error('ERR_FILE_NOT_FOUND'));
    guard.didFailLoad({
      errorCode: -6,
      errorDescription: 'ERR_FILE_NOT_FOUND',
      validatedURL: 'app://hardcore/index.html',
      isMainFrame: true,
    });

    expect(onFailure).toHaveBeenCalledExactlyOnceWith(
      expect.objectContaining({ message: 'ERR_FILE_NOT_FOUND' })
    );
  });
});
