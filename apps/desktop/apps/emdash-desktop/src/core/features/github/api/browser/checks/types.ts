import type { PullRequestCheck } from '@core/services/pull-requests/api';

export type CheckRun = PullRequestCheck;

export interface CheckRunsSummary {
  total: number;
  completed: number;
  passed: number;
  failed: number;
  pending: number;
  skipped: number;
  cancelled: number;
}
