import { Markdown } from '@emdash/ui/react/components';
import { RelativeTime } from '@emdash/ui/react/primitives';
import { ExternalLink, MessageSquare } from 'lucide-react';
import { useMemo } from 'react';
import { openExternal } from '@core/primitives/desktop-host/browser/host-client';
import { useMarkdownLinkOpener } from '@core/primitives/external-links/browser';
import { cn } from '@core/primitives/styling/browser/cn';
import {
  sortPullRequestConversationItems,
  type PullRequestConversationItem,
} from './pull-request-conversation';

function commentAuthorLabel(comment: PullRequestConversationItem): string {
  return comment.author?.displayName ?? comment.author?.userName ?? 'Unknown author';
}

function commentLocationLabel(comment: PullRequestConversationItem): string | null {
  if (!comment.path) return null;
  return comment.line ? `${comment.path}:${comment.line}` : comment.path;
}

function isBotAuthor(comment: PullRequestConversationItem): boolean {
  return comment.author?.userName.endsWith('[bot]') ?? false;
}

function CommentItem({ comment }: { comment: PullRequestConversationItem }) {
  const location = commentLocationLabel(comment);
  const author = commentAuthorLabel(comment);
  const avatarRadiusClass = isBotAuthor(comment) ? 'rounded' : 'rounded-full';
  const openLink = useMarkdownLinkOpener();

  return (
    <div className="group relative flex w-full min-w-0 gap-2 rounded-md px-3 py-2 text-left hover:bg-background-1">
      {comment.author?.avatarUrl ? (
        <img
          src={comment.author.avatarUrl}
          alt={author}
          className={cn('mt-0.5 size-5 shrink-0', avatarRadiusClass)}
        />
      ) : (
        <div
          className={cn(
            'mt-0.5 flex size-5 shrink-0 items-center justify-center bg-background-2 text-foreground-muted',
            avatarRadiusClass
          )}
        >
          <MessageSquare className="size-3" />
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="flex min-w-0 items-center gap-1.5 text-xs text-foreground-muted">
          <span className="truncate font-medium text-foreground">{author}</span>
          <span className="shrink-0 text-foreground-passive">/</span>
          <RelativeTime compact value={comment.createdAt} className="shrink-0" />
          {comment.isResolved && (
            <>
              <span className="shrink-0 text-foreground-passive">/</span>
              <span className="shrink-0 text-foreground-passive">Resolved</span>
            </>
          )}
        </div>
        {location && (
          <div className="mt-0.5 truncate font-mono text-tiny text-foreground-passive">
            {location}
          </div>
        )}
        <div
          className={cn(
            'mt-1 break-words text-xs leading-relaxed text-foreground-muted [&_*:last-child]:mb-0 [&_p]:mb-1.5',
            comment.isOutdated && 'text-foreground-passive'
          )}
        >
          <Markdown content={comment.body} variant="compact" allowHtml onOpenLink={openLink} />
        </div>
      </div>
      <button
        className="absolute top-2 right-3 hidden items-center justify-center rounded bg-background-1 px-1 py-0.5 text-foreground-muted group-hover:flex hover:text-foreground"
        onClick={() => void openExternal(comment.url)}
      >
        <ExternalLink className="size-3.5" />
      </button>
    </div>
  );
}

export function CommentsList({
  comments,
  isLoading,
  error,
}: {
  comments: PullRequestConversationItem[];
  isLoading?: boolean;
  error?: Error | null;
}) {
  const sorted = useMemo(() => [...comments].sort(sortPullRequestConversationItems), [comments]);

  if (isLoading && sorted.length === 0) {
    return <div className="px-3 py-2 text-xs text-foreground-passive">Loading comments...</div>;
  }

  if (error && sorted.length === 0) {
    return <div className="px-3 py-2 text-xs text-foreground-passive">Unable to load comments</div>;
  }

  if (sorted.length === 0) {
    return <div className="px-3 py-2 text-xs text-foreground-passive">No comments available</div>;
  }

  return (
    <div className="flex flex-col gap-[1px]">
      {sorted.map((comment) => (
        <CommentItem key={comment.id} comment={comment} />
      ))}
      {isLoading && (
        <div className="px-3 py-2 text-xs text-foreground-passive">Loading comments...</div>
      )}
      {error && (
        <div className="px-3 py-2 text-xs text-foreground-passive">Unable to load comments</div>
      )}
    </div>
  );
}
