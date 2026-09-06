import { createManualClock } from '@emdash/shared/testing';
import { observable } from 'mobx';
import { describe, expect, it } from 'vitest';
import type { ProjectHostAccessState } from '@core/features/projects/api/browser/stores/project-context';
import type { PullRequest } from '@core/services/pull-requests/api';
import type { GitCheckoutStore } from '../../../browser/stores/git-checkout-store';
import type { GitRepositoryStore } from './git-repository-store';
import { PrStore } from './pr-store';
import { TaskPrAssociationStore } from './task-pr-association-store';

const pullRequest = {
  url: 'https://github.com/example/repo/pull/1',
  status: 'open',
  title: 'Retained pull request',
} as PullRequest;

describe('PrStore Host observations', () => {
  it('retains observed PRs as stale and distinguishes never-observed data', () => {
    const state = observable.box<ProjectHostAccessState>(
      { kind: 'ready', hostGeneration: 1 },
      { deep: false }
    );
    const repository = {
      observeHost: <T>(
        observation: { kind: 'never-observed' } | { kind: 'observed'; value: T; observedAt: number }
      ) => {
        if (observation.kind === 'never-observed') return { kind: 'unavailable' as const };
        return state.get().kind === 'ready'
          ? { ...observation, kind: 'fresh' as const }
          : { ...observation, kind: 'stale' as const };
      },
    } as GitRepositoryStore;
    const association = new TaskPrAssociationStore(createManualClock(1_786_000_000_000));
    association.setAssociation([pullRequest], { kind: 'unknown' });
    const store = new PrStore(
      'project-1',
      'workspace-1',
      repository,
      {} as GitCheckoutStore,
      association
    );

    expect(store.pullRequestsObservation).toMatchObject({
      kind: 'fresh',
      value: [pullRequest],
      observedAt: 1_786_000_000_000,
    });

    state.set({ kind: 'degraded', situation: 'offline', recovery: 'automatic' });
    expect(store.pullRequestsObservation).toMatchObject({
      kind: 'stale',
      value: [pullRequest],
    });

    expect(store.pullRequests).toEqual([pullRequest]);
    expect(store.pullRequestsObservation.kind).toBe('stale');
    store.dispose();

    const neverObserved = new PrStore(
      'project-1',
      'workspace-2',
      repository,
      {} as GitCheckoutStore,
      new TaskPrAssociationStore()
    );
    expect(neverObserved.pullRequestsObservation).toEqual({ kind: 'unavailable' });
    neverObserved.dispose();
  });
});
