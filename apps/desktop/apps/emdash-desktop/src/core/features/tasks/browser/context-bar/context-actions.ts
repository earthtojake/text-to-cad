import type { DraftComment } from '@core/features/source-control/api/browser/diff-view/stores/draft-comments-store';
import { buildIssueContextText } from '@core/primitives/issues/api';
import { formatCommentsForAgent } from '@core/primitives/line-comments/api';
import type { LinkedIssue } from '@core/primitives/linked-issues/api';
import type { PromptLibraryPrompt } from '@core/primitives/prompt-library/api';

export { buildIssueContextText } from '@core/primitives/issues/api';

// ─── Types ───────────────────────────────────────────────────────────────────

export type ContextActionKind = 'linked-issue' | 'draft-comments' | 'prompt';

export interface IssueContextAction {
  id: string;
  kind: 'linked-issue';
  provider: LinkedIssue['provider'];
  issue: LinkedIssue;
}

export interface DraftCommentsContextAction {
  id: string;
  kind: 'draft-comments';
  comments: DraftComment[];
  commentCount: number;
  fileCount: number;
}

export interface PromptContextAction {
  id: string;
  kind: 'prompt';
  prompt: PromptLibraryPrompt;
}

export type ContextAction = IssueContextAction | DraftCommentsContextAction | PromptContextAction;

// ─── Text building ───────────────────────────────────────────────────────────

export function buildContextActionText(action: ContextAction): string {
  switch (action.kind) {
    case 'linked-issue':
      return buildIssueContextText(action.issue);
    case 'draft-comments':
      return formatCommentsForAgent(action.comments, { includeIntro: false });
    case 'prompt':
      return action.prompt.prompt;
  }
}

// ─── Builders ────────────────────────────────────────────────────────────────

export function buildLinkedIssueContextAction(issue?: LinkedIssue): IssueContextAction | null {
  if (!issue) return null;
  return {
    id: `linked-issue:${issue.provider}:${issue.identifier}`,
    kind: 'linked-issue',
    provider: issue.provider,
    issue,
  };
}

export function buildDraftCommentsContextAction(
  comments: DraftComment[]
): DraftCommentsContextAction | null {
  if (comments.length === 0) return null;
  const fileCount = new Set(comments.map((c) => c.filePath)).size;
  return {
    id: 'draft-comments',
    kind: 'draft-comments',
    comments,
    commentCount: comments.length,
    fileCount,
  };
}

export function buildPromptLibraryContextActions(
  prompts: PromptLibraryPrompt[]
): PromptContextAction[] {
  return prompts
    .filter((p) => p.prompt.trim().length > 0)
    .map((p) => ({
      id: `prompt:${p.id}`,
      kind: 'prompt' as const,
      prompt: p,
    }));
}

export function buildTaskContextActions(
  issue: LinkedIssue | undefined,
  comments: DraftComment[],
  prompts: PromptLibraryPrompt[]
): ContextAction[] {
  return [
    buildLinkedIssueContextAction(issue),
    buildDraftCommentsContextAction(comments),
    ...buildPromptLibraryContextActions(prompts),
  ].filter((a): a is ContextAction => a !== null);
}
