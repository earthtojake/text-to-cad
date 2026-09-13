import { describe, expect, it } from 'vitest';
import type { PrDriftObservedFacts } from './derive-pr-checkout-drift';
import { derivePrCheckoutDrift } from './derive-pr-checkout-drift';

const HEAD = 'aaaa000000000000000000000000000000000000';
const MOVED_HEAD = 'bbbb111111111111111111111111111111111111';

function observedFacts(overrides: Partial<PrDriftObservedFacts> = {}): PrDriftObservedFacts {
  return { headOid: HEAD, ahead: 0, behind: 0, ...overrides };
}

describe('derivePrCheckoutDrift', () => {
  it('reads in-sync when the observed head equals the cached PR head, carrying syncedAt', () => {
    const drift = derivePrCheckoutDrift({
      observed: observedFacts(),
      pr: { headRefOid: HEAD },
      syncedAt: 1_700_000_000_000,
    });

    expect(drift).toEqual({ kind: 'in-sync', syncedAt: 1_700_000_000_000 });
  });

  it('flags prMoved when the cache head differs and nothing local explains it (ahead 0)', () => {
    const drift = derivePrCheckoutDrift({
      observed: observedFacts({ ahead: 0, behind: 0 }),
      pr: { headRefOid: MOVED_HEAD },
      syncedAt: 42,
    });

    expect(drift).toEqual({
      kind: 'drifted',
      localAhead: false,
      prMoved: true,
      syncedAt: 42,
    });
  });

  it('flags prMoved when the tracking ref itself has commits the checkout lacks (behind > 0)', () => {
    const drift = derivePrCheckoutDrift({
      observed: observedFacts({ ahead: 2, behind: 3 }),
      pr: { headRefOid: MOVED_HEAD },
      syncedAt: 42,
    });

    expect(drift).toEqual({
      kind: 'drifted',
      localAhead: true,
      prMoved: true,
      syncedAt: 42,
    });
  });

  it('surfaces localAhead with an honest-null prMoved when local commits could explain the difference', () => {
    const drift = derivePrCheckoutDrift({
      observed: observedFacts({ ahead: 2, behind: 0 }),
      pr: { headRefOid: MOVED_HEAD },
      syncedAt: 42,
    });

    expect(drift).toEqual({
      kind: 'drifted',
      localAhead: true,
      prMoved: null,
      syncedAt: 42,
    });
  });

  it('degrades fork checkouts without a resolvable tracking ref to umbrella drifted with null flags', () => {
    const drift = derivePrCheckoutDrift({
      observed: observedFacts({ ahead: null, behind: null }),
      pr: { headRefOid: MOVED_HEAD },
      syncedAt: 42,
    });

    expect(drift).toEqual({
      kind: 'drifted',
      localAhead: null,
      prMoved: null,
      syncedAt: 42,
    });
  });

  it('reads unknown when the workspace is unobserved (old host / v1 payload)', () => {
    const drift = derivePrCheckoutDrift({
      observed: null,
      pr: { headRefOid: HEAD },
      syncedAt: 42,
    });

    expect(drift).toEqual({ kind: 'unknown' });
  });

  it('reads unknown when the head OID probe degraded to null — never a false in-sync', () => {
    const drift = derivePrCheckoutDrift({
      observed: observedFacts({ headOid: null }),
      pr: { headRefOid: HEAD },
      syncedAt: 42,
    });

    expect(drift).toEqual({ kind: 'unknown' });
  });

  it('reads unknown when no PR is associated or the PR is not in the cache', () => {
    const drift = derivePrCheckoutDrift({
      observed: observedFacts(),
      pr: null,
      syncedAt: 42,
    });

    expect(drift).toEqual({ kind: 'unknown' });
  });

  it('reads unknown when the cached PR carries no head OID', () => {
    const drift = derivePrCheckoutDrift({
      observed: observedFacts(),
      pr: { headRefOid: '' },
      syncedAt: 42,
    });

    expect(drift).toEqual({ kind: 'unknown' });
  });

  it('carries a null syncedAt honestly when the cache has never reported a sync stamp', () => {
    const inSync = derivePrCheckoutDrift({
      observed: observedFacts(),
      pr: { headRefOid: HEAD },
      syncedAt: null,
    });
    const drifted = derivePrCheckoutDrift({
      observed: observedFacts(),
      pr: { headRefOid: MOVED_HEAD },
      syncedAt: null,
    });

    expect(inSync).toEqual({ kind: 'in-sync', syncedAt: null });
    expect(drifted).toMatchObject({ kind: 'drifted', syncedAt: null });
  });
});
