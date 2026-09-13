import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { checkoutDriftLabel, checkoutDriftSyncNote } from './checkout-drift-line';

describe('checkoutDriftLabel', () => {
  it('makes no claim for unknown', () => {
    expect(checkoutDriftLabel({ kind: 'unknown' })).toBeNull();
  });

  it('labels in-sync', () => {
    expect(checkoutDriftLabel({ kind: 'in-sync', syncedAt: 1 })).toBe(
      'Checkout in sync with PR head'
    );
  });

  it('labels drifted with only the flags that are honestly true', () => {
    expect(
      checkoutDriftLabel({ kind: 'drifted', localAhead: false, prMoved: true, syncedAt: 1 })
    ).toBe('Checkout differs from PR head (PR head moved)');
    expect(
      checkoutDriftLabel({ kind: 'drifted', localAhead: true, prMoved: null, syncedAt: 1 })
    ).toBe('Checkout differs from PR head (local commits ahead)');
    expect(
      checkoutDriftLabel({ kind: 'drifted', localAhead: true, prMoved: true, syncedAt: 1 })
    ).toBe('Checkout differs from PR head (PR head moved, local commits ahead)');
  });

  it('labels the umbrella drifted state when flags are honest nulls (fork degrade)', () => {
    expect(
      checkoutDriftLabel({ kind: 'drifted', localAhead: null, prMoved: null, syncedAt: 1 })
    ).toBe('Checkout differs from PR head');
  });
});

describe('checkoutDriftSyncNote', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-08-07T12:00:00.000Z'));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('stamps the state with the cache sync time', () => {
    const syncedAt = Date.parse('2026-08-07T11:55:00.000Z');
    expect(checkoutDriftSyncNote({ kind: 'in-sync', syncedAt })).toBe(
      'as of last sync 5 minutes ago'
    );
  });

  it('stays silent when no sync stamp is known', () => {
    expect(checkoutDriftSyncNote({ kind: 'in-sync', syncedAt: null })).toBeNull();
    expect(checkoutDriftSyncNote({ kind: 'unknown' })).toBeNull();
  });
});
