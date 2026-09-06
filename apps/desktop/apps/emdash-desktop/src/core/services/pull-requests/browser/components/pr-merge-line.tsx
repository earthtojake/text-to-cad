import { Tooltip } from '@emdash/ui/react/primitives';
import { ArrowRight, GitBranch } from 'lucide-react';
import { parseRepositoryRef } from '@core/primitives/repository/api';
import { cn } from '@core/primitives/styling/browser/cn';
import type { PullRequest } from '@core/services/pull-requests/api';

export function PrMergeLine({ pr, className }: { pr: PullRequest; className?: string }) {
  const author = pr.author?.userName;
  const baseOwner = parseRepositoryRef(pr.repositoryUrl)?.owner;
  const baseBranch = pr.baseRefName;
  const headOwner = parseRepositoryRef(pr.headRepositoryUrl)?.owner ?? author;
  const headBranch = pr.headRefName;
  const actionText = getPrMergeLineActionText(pr.status);

  return (
    <div className={cn('flex min-w-0 flex-col gap-1 text-xs text-foreground-muted', className)}>
      <div className="flex flex-wrap items-center gap-x-1">
        {author && <span className="font-medium">{author}</span>}
        <span>{actionText}</span>
      </div>
      <div className="flex min-w-0 items-center gap-1">
        <PrBranchBadge owner={headOwner} branch={headBranch} />
        <ArrowRight className="size-3 shrink-0 text-foreground-passive" />
        <PrBranchBadge owner={baseOwner} branch={baseBranch} />
      </div>
    </div>
  );
}

export function getPrMergeLineActionText(status: PullRequest['status']) {
  switch (status) {
    case 'merged':
      return 'merged';
    case 'closed':
      return 'was closed without merging';
    case 'open':
      return 'wants to merge';
  }
}

function PrBranchBadge({ owner, branch }: { owner?: string; branch: string }) {
  return (
    <Tooltip.Root>
      <Tooltip.Trigger className="min-w-0">
        <span className="flex min-w-0 items-center gap-1 rounded-md bg-background-2 px-1 py-0.5 font-mono text-micro font-medium">
          <GitBranch className="size-3 shrink-0" />
          <span className="truncate">
            {owner}:{branch}
          </span>
        </span>
      </Tooltip.Trigger>
      <Tooltip.Content>
        {owner}:{branch}
      </Tooltip.Content>
    </Tooltip.Root>
  );
}
