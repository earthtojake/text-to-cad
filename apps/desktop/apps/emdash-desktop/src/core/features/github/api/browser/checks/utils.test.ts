import { describe, expect, it } from 'vitest';
import type { CheckRun } from './types';
import { sortCheckRunsByLatest } from './utils';

function makeCheck(overrides: Partial<CheckRun> = {}): CheckRun {
  return {
    id: 'check-1',
    pullRequestUrl: 'https://github.com/acme/repo/pull/1',
    commitSha: 'head',
    name: 'CI',
    status: 'COMPLETED',
    conclusion: 'SUCCESS',
    detailsUrl: null,
    startedAt: null,
    completedAt: null,
    workflowName: null,
    appName: null,
    appLogoUrl: null,
    ...overrides,
  };
}

describe('sortCheckRunsByLatest', () => {
  it('orders runs newest first regardless of their result', () => {
    const oldFailure = makeCheck({
      id: 'old-failure',
      name: 'CI (old)',
      conclusion: 'FAILURE',
      startedAt: '2026-07-18T08:00:00.000Z',
    });
    const latestSuccess = makeCheck({
      id: 'latest-success',
      name: 'CI (latest)',
      startedAt: '2026-07-18T09:00:00.000Z',
    });

    expect(sortCheckRunsByLatest([oldFailure, latestSuccess])).toEqual([latestSuccess, oldFailure]);
  });

  it('falls back to completion time and keeps runs without a timestamp last', () => {
    const unknownTime = makeCheck({ id: 'unknown-time' });
    const completed = makeCheck({
      id: 'completed',
      completedAt: '2026-07-18T09:00:00.000Z',
    });

    expect(sortCheckRunsByLatest([unknownTime, completed])).toEqual([completed, unknownTime]);
  });

  it('does not mutate the source list', () => {
    const older = makeCheck({ id: 'older', startedAt: '2026-07-18T08:00:00.000Z' });
    const newer = makeCheck({ id: 'newer', startedAt: '2026-07-18T09:00:00.000Z' });
    const checks = [older, newer];

    sortCheckRunsByLatest(checks);

    expect(checks).toEqual([older, newer]);
  });
});
