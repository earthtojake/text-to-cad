import type { PullRequest, PullRequestComment } from '@core/services/pull-requests/api';

export type PullRequestDescriptionItem = {
  id: string;
  pullRequestUrl: string;
  kind: 'description';
  body: string;
  url: string;
  author: PullRequest['author'];
  path: null;
  line: null;
  isResolved: false;
  isOutdated: false;
  createdAt: string;
  updatedAt: string;
};

export type PullRequestConversationItem = PullRequestDescriptionItem | PullRequestComment;

function descriptionItemForPr(pr: PullRequest): PullRequestDescriptionItem | null {
  const body = pr.description?.trim();
  if (!body) return null;

  return {
    id: `description:${pr.url}`,
    pullRequestUrl: pr.url,
    kind: 'description',
    body,
    url: pr.url,
    author: pr.author,
    path: null,
    line: null,
    isResolved: false,
    isOutdated: false,
    createdAt: pr.createdAt,
    updatedAt: pr.updatedAt,
  };
}

export function sortPullRequestConversationItems(
  a: PullRequestConversationItem,
  b: PullRequestConversationItem
): number {
  if (a.kind === 'description' && b.kind !== 'description') return -1;
  if (a.kind !== 'description' && b.kind === 'description') return 1;

  const createdAtDelta = new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime();
  if (createdAtDelta !== 0) return createdAtDelta;

  return new Date(a.updatedAt).getTime() - new Date(b.updatedAt).getTime();
}

export function buildPullRequestConversationItems(
  pr: PullRequest,
  comments: PullRequestComment[]
): PullRequestConversationItem[] {
  const description = descriptionItemForPr(pr);
  return [...(description ? [description] : []), ...comments];
}
