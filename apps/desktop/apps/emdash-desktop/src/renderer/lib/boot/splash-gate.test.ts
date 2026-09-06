import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { raceSplashGate, waitForActiveProjectContext } from './splash-gate';

describe('raceSplashGate', () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('resolves ready when every condition settles before the deadline', async () => {
    let resolveSlow: () => void = () => {};
    const slow = new Promise<void>((resolve) => {
      resolveSlow = resolve;
    });

    const outcome = raceSplashGate([Promise.resolve(), slow], 3000);

    await vi.advanceTimersByTimeAsync(1000);
    resolveSlow();
    await expect(outcome).resolves.toBe('ready');
  });

  it('resolves timeout when a condition is still pending at the deadline', async () => {
    const never = new Promise<void>(() => {});

    const outcome = raceSplashGate([Promise.resolve(), never], 3000);

    await vi.advanceTimersByTimeAsync(3000);
    await expect(outcome).resolves.toBe('timeout');
  });

  it('counts a rejected condition as settled instead of holding the splash', async () => {
    const failed = Promise.reject(new Error('backend never came up'));

    const outcome = raceSplashGate([failed, Promise.resolve()], 3000);

    await vi.advanceTimersByTimeAsync(0);
    await expect(outcome).resolves.toBe('ready');
  });

  it('resolves ready immediately with no conditions', async () => {
    const outcome = raceSplashGate([], 3000);

    await vi.advanceTimersByTimeAsync(0);
    await expect(outcome).resolves.toBe('ready');
  });

  it('keeps the timeout outcome when conditions settle after the deadline', async () => {
    let resolveLate: () => void = () => {};
    const late = new Promise<void>((resolve) => {
      resolveLate = resolve;
    });

    const outcome = raceSplashGate([late], 3000);

    await vi.advanceTimersByTimeAsync(3000);
    resolveLate();
    await vi.advanceTimersByTimeAsync(0);
    await expect(outcome).resolves.toBe('timeout');
  });
});

describe('waitForActiveProjectContext', () => {
  it('settles after desktop context hydration without waiting for Host attachment', async () => {
    const hydrateProjectContext = vi.fn().mockResolvedValue(undefined);

    await expect(
      waitForActiveProjectContext({
        navigationRestored: Promise.resolve(),
        projectsLoaded: Promise.resolve(),
        activeProjectId: () => 'project-id',
        hydrateProjectContext,
      })
    ).resolves.toBeUndefined();

    expect(hydrateProjectContext).toHaveBeenCalledWith('project-id');
  });
});
