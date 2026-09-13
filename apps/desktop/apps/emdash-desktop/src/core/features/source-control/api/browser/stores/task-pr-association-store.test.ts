import { createManualClock } from '@emdash/shared/testing';
import { describe, expect, it } from 'vitest';
import type { PullRequest } from '@core/services/pull-requests/api';
import { TaskPrAssociationStore } from './task-pr-association-store';

const pullRequest = {
  url: 'https://github.com/emdash/emdash/pull/42',
  repositoryUrl: 'https://github.com/emdash/emdash',
  title: 'Original title',
} as PullRequest;

describe('TaskPrAssociationStore', () => {
  it('distinguishes unknown, none, and associated PR state', () => {
    const store = new TaskPrAssociationStore(createManualClock(1_786_000_000_000));

    expect(store.state).toEqual({ kind: 'unknown' });
    expect(store.pullRequests).toEqual([]);

    store.setAssociation([pullRequest], { kind: 'in-sync', syncedAt: 1 });

    expect(store.state).toMatchObject({
      kind: 'associated',
      pullRequests: [pullRequest],
      observedAt: 1_786_000_000_000,
    });
    expect(store.checkoutDrift).toEqual({ kind: 'in-sync', syncedAt: 1 });

    store.setAssociation([], { kind: 'unknown' });

    expect(store.state).toEqual({ kind: 'none', observedAt: 1_786_000_000_000 });
    expect(store.pullRequests).toEqual([]);
    expect(store.checkoutDrift).toEqual({ kind: 'unknown' });
  });

  it('refreshes details only for an already-associated PR', () => {
    const store = new TaskPrAssociationStore();
    const refreshed = { ...pullRequest, title: 'Refreshed title' };

    store.updateAssociatedPr(refreshed);
    expect(store.state).toEqual({ kind: 'unknown' });

    store.setAssociation([pullRequest], { kind: 'unknown' });
    store.updateAssociatedPr(refreshed);

    expect(store.pullRequests).toEqual([refreshed]);
  });
});
