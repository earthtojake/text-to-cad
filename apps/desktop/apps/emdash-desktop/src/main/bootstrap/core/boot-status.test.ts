import { beforeEach, describe, expect, it, vi } from 'vitest';
import type * as BootStatus from './boot-status';

describe('boot-status', () => {
  let bootStatus: typeof BootStatus;

  beforeEach(async () => {
    vi.resetModules();
    bootStatus = await import('./boot-status');
  });

  it('does not settle on a single signal', () => {
    const settled = vi.fn();
    bootStatus.onBootSettled(settled);

    bootStatus.reportBootSuccessSignal('backend');
    expect(bootStatus.isBootSettled()).toBe(false);
    expect(settled).not.toHaveBeenCalled();

    expect(bootStatus.bootSuccessSignalsSeen()).toEqual({ backend: true, windowLoaded: false });
  });

  it('settles exactly once when both signals fire, in either order', () => {
    const settled = vi.fn();
    bootStatus.onBootSettled(settled);

    bootStatus.reportBootSuccessSignal('window-load');
    bootStatus.reportBootSuccessSignal('backend');

    expect(bootStatus.isBootSettled()).toBe(true);
    expect(settled).toHaveBeenCalledOnce();

    // Repeated signals (e.g. a window reload firing did-finish-load again)
    // never re-fire the settled callbacks.
    bootStatus.reportBootSuccessSignal('window-load');
    expect(settled).toHaveBeenCalledOnce();
  });

  it('runs a late subscriber immediately when already settled', () => {
    bootStatus.reportBootSuccessSignal('backend');
    bootStatus.reportBootSuccessSignal('window-load');

    const settled = vi.fn();
    bootStatus.onBootSettled(settled);
    expect(settled).toHaveBeenCalledOnce();
  });
});
