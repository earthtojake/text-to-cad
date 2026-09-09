import { formatDistanceToNow } from 'date-fns';
import type { CheckRun, CheckRunsSummary } from './types';

export type CheckRunBucket = 'pass' | 'fail' | 'pending' | 'skipping' | 'cancel';

/** Derive a display bucket from a check's raw status and conclusion fields. */
export function computeCheckBucket(check: CheckRun): CheckRunBucket {
  const status = check.status?.toUpperCase() ?? '';
  const conclusion = check.conclusion?.toUpperCase() ?? null;

  if (
    status === 'IN_PROGRESS' ||
    status === 'QUEUED' ||
    status === 'WAITING' ||
    status === 'PENDING'
  ) {
    return 'pending';
  }
  if (!conclusion || conclusion === 'NEUTRAL') return 'skipping';
  if (conclusion === 'SUCCESS') return 'pass';
  if (conclusion === 'FAILURE' || conclusion === 'TIMED_OUT' || conclusion === 'ACTION_REQUIRED')
    return 'fail';
  if (conclusion === 'CANCELLED' || conclusion === 'STALE') return 'cancel';
  if (conclusion === 'SKIPPED') return 'skipping';
  return 'skipping';
}

export function computeCheckRunsSummary(checks: CheckRun[]): CheckRunsSummary {
  const summary: CheckRunsSummary = {
    total: checks.length,
    completed: 0,
    passed: 0,
    failed: 0,
    pending: 0,
    skipped: 0,
    cancelled: 0,
  };
  for (const c of checks) {
    const bucket = computeCheckBucket(c);
    switch (bucket) {
      case 'pass':
        summary.passed++;
        break;
      case 'fail':
        summary.failed++;
        break;
      case 'pending':
        summary.pending++;
        break;
      case 'skipping':
        summary.skipped++;
        break;
      case 'cancel':
        summary.cancelled++;
        break;
    }
  }
  summary.completed = summary.total - summary.pending;
  return summary;
}

export function sortCheckRunsByLatest(checks: CheckRun[]): CheckRun[] {
  return [...checks].sort((a, b) => {
    const aTimestamp = Date.parse(a.startedAt ?? a.completedAt ?? '');
    const bTimestamp = Date.parse(b.startedAt ?? b.completedAt ?? '');
    const aTime = Number.isNaN(aTimestamp) ? Number.NEGATIVE_INFINITY : aTimestamp;
    const bTime = Number.isNaN(bTimestamp) ? Number.NEGATIVE_INFINITY : bTimestamp;
    return bTime - aTime;
  });
}

export function formatRelativeTime(dateStr: string): string {
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return '';
  return formatDistanceToNow(date, { addSuffix: true });
}

export function formatCheckDuration(startedAt?: string, completedAt?: string): string | null {
  if (!startedAt || !completedAt) return null;
  const start = new Date(startedAt).getTime();
  const end = new Date(completedAt).getTime();
  if (isNaN(start) || isNaN(end)) return null;
  const diffMs = end - start;
  if (diffMs < 0) return null;

  const totalSeconds = Math.floor(diffMs / 1000);
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);

  if (hours > 0) return `${hours}h ${minutes}m`;
  if (minutes > 0) return `${minutes}m ${totalSeconds % 60}s`;
  return '<1m';
}
