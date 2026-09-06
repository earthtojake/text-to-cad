import { EmptyState } from '@emdash/ui/react/components';
import { CheckCircle2, ExternalLink, Loader2, MinusCircle, XCircle } from 'lucide-react';
import { observer } from 'mobx-react-lite';
import { useMemo } from 'react';
import {
  computeCheckBucket,
  formatCheckDuration,
  sortCheckRunsByLatest,
  type CheckRun,
  type CheckRunBucket,
} from '@core/features/github/api/browser/checks';
import { openExternal } from '@core/primitives/desktop-host/browser/host-client';
import type { PullRequest, PullRequestComment } from '@core/services/pull-requests/api';
import { useSyncCheckRuns } from '../../../state/use-check-runs';
import { CommentsList } from './comments-list';
import { buildPullRequestConversationItems } from './pull-request-conversation';
import { usePullRequestComments } from './use-pull-request-comments';

const EMPTY_COMMENTS: PullRequestComment[] = [];

export function BucketIcon({ bucket }: { bucket: CheckRunBucket }) {
  switch (bucket) {
    case 'pass':
      return <CheckCircle2 className="size-3.5 shrink-0 text-foreground-success" />;
    case 'fail':
      return <XCircle className="size-3.5 shrink-0 text-foreground-destructive" />;
    case 'pending':
      return <Loader2 className="size-3.5 shrink-0 animate-spin text-foreground-warning" />;
    case 'skipping':
    case 'cancel':
      return <MinusCircle className="size-3.5 shrink-0 text-foreground-muted" />;
  }
}

export function CheckRunItem({ check }: { check: CheckRun }) {
  const bucket = computeCheckBucket(check);
  const duration = formatCheckDuration(
    check.startedAt ?? undefined,
    check.completedAt ?? undefined
  );
  const subtitle = check.appName ?? check.workflowName;
  const detailsUrl = check.detailsUrl;
  return (
    <div className="group relative flex items-center gap-2 rounded-md px-3 py-2 hover:bg-background-1">
      <div className="flex min-w-0 flex-1 flex-col gap-1">
        <div className="flex items-center gap-2">
          <BucketIcon bucket={bucket} />
          <div className="truncate text-sm">{check.name}</div>
          {check.appLogoUrl ? (
            <img
              src={check.appLogoUrl}
              alt={check.appName ?? ''}
              className="size-4 shrink-0 rounded opacity-60"
            />
          ) : null}
        </div>
        {subtitle && (
          <div className="flex w-full justify-start truncate text-xs text-foreground-passive">
            {subtitle}
          </div>
        )}
      </div>
      <div className="flex shrink-0 items-center gap-2">
        {duration && <span className="text-xs text-foreground-passive">{duration}</span>}
        {detailsUrl && (
          <button
            type="button"
            aria-label={`Open ${check.name} check details`}
            className="absolute top-1/2 right-3 hidden -translate-y-1/2 items-center justify-center rounded bg-background-1 px-1 py-0.5 text-foreground-muted group-hover:flex hover:text-foreground"
            onClick={() => void openExternal(detailsUrl)}
          >
            <ExternalLink className="size-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

export function ChecksList({ checks }: { checks: CheckRun[] }) {
  const sorted = useMemo(() => sortCheckRunsByLatest(checks), [checks]);

  if (sorted.length === 0) {
    return <div className="px-3 py-2 text-xs text-foreground-passive">No checks available</div>;
  }

  return (
    <div className="flex flex-col gap-[1px]">
      {sorted.map((check, i) => (
        <CheckRunItem key={`${check.name}-${i}`} check={check} />
      ))}
    </div>
  );
}

export const PrChecksList = observer(function PrChecksList({
  projectId,
  pr,
}: {
  projectId: string;
  pr: PullRequest;
}) {
  const { checks } = useSyncCheckRuns(pr);
  const commentsQuery = usePullRequestComments(projectId, pr);
  const comments = commentsQuery.data ?? EMPTY_COMMENTS;
  const conversationItems = useMemo(
    () => buildPullRequestConversationItems(pr, comments),
    [pr, comments]
  );

  if (checks.length === 0 && conversationItems.length === 0 && !commentsQuery.isLoading) {
    return <EmptyState label="No checks or comments" description="Nothing available yet" />;
  }

  return (
    <div className="flex flex-col gap-4 py-2">
      <section>
        <div className="px-3 pb-1 text-tiny font-medium text-foreground-passive uppercase">
          Checks
        </div>
        <ChecksList checks={checks} />
      </section>
      <section>
        <div className="px-3 pb-1 text-tiny font-medium text-foreground-passive uppercase">
          Comments
        </div>
        <CommentsList
          comments={conversationItems}
          isLoading={commentsQuery.isLoading}
          error={commentsQuery.error}
        />
      </section>
    </div>
  );
});
