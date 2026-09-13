import { describe, expect, it } from 'vitest';
import type { DraftComment } from '@core/features/source-control/api/browser/diff-view/stores/draft-comments-store';
import {
  buildDraftCommentsContextAction,
  buildIssueContextText,
  buildLinkedIssueContextAction,
  buildPromptLibraryContextActions,
  buildTaskContextActions,
} from '@core/features/tasks/browser/context-bar/context-actions';
import {
  getDraftCommentTargetKey,
  type DraftCommentTarget,
} from '@core/primitives/line-comments/api';
import type { LinkedIssue } from '@core/primitives/linked-issues/api';

function makeIssue(overrides: Partial<LinkedIssue> = {}): LinkedIssue {
  return {
    provider: 'github',
    identifier: 'EMD-123',
    title: 'Fix task context injection behavior',
    url: 'https://example.com/issues/EMD-123',
    description: 'Ensure issue context can be injected from the context bar.',
    status: 'In Progress',
    assignees: ['alice', 'bob'],
    project: 'Infra',
    updatedAt: '2026-04-15T11:27:38.662Z',
    fetchedAt: '2026-04-15T15:49:46.788Z',
    ...overrides,
  };
}

function makeDraftComment(overrides: Partial<DraftComment> = {}): DraftComment {
  const target: DraftCommentTarget = overrides.target ?? {
    kind: 'working-tree',
    group: 'disk',
    path: overrides.filePath ?? 'src/foo.ts',
  };
  return {
    id: crypto.randomUUID(),
    taskId: 'task-1',
    filePath: target.path,
    target,
    targetKey: getDraftCommentTargetKey(target),
    lineNumber: 10,
    lineContent: 'const x = 1;',
    content: 'This looks wrong.',
    createdAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
    ...overrides,
  };
}

describe('buildIssueContextText', () => {
  it('normalizes field whitespace and produces a newline-free string for basic fields', () => {
    const text = buildIssueContextText(
      makeIssue({ description: 'Line one.\nLine two.\n\nLine three.' })
    );

    expect(text).toContain('Provider: Github');
    expect(text).toContain('Identifier: EMD-123');
    expect(text).toContain('Title: Fix task context injection behavior');
    expect(text).toContain('URL: https://example.com/issues/EMD-123');
    expect(text).toContain('Description: Line one. Line two. Line three.');
    expect(text).toContain('Status: In Progress');
    expect(text).toContain('Assignees: alice, bob');
    expect(text).toContain('Project: Infra');
    expect(text).not.toMatch(/\r|\n/);
  });

  it('does not truncate long descriptions', () => {
    const longDescription = 'A'.repeat(500);
    const text = buildIssueContextText(makeIssue({ description: longDescription }));
    expect(text).toContain(`Description: ${longDescription}`);
  });

  it('appends provider-specific context with preserved newlines', () => {
    const text = buildIssueContextText(
      makeIssue({
        provider: 'linear',
        context: 'Linear issue activity\n\nComments:\n- 2026-04-17 by Jona: Looks good',
      })
    );

    expect(text).toContain(
      'Context:\nLinear issue activity\n\nComments:\n- 2026-04-17 by Jona: Looks good'
    );
  });
});

describe('buildLinkedIssueContextAction', () => {
  it('returns null when no issue is linked', () => {
    expect(buildLinkedIssueContextAction(undefined)).toBeNull();
  });

  it('builds an action with the correct id, kind, provider and issue', () => {
    const issue = makeIssue();
    const action = buildLinkedIssueContextAction(issue);

    expect(action).not.toBeNull();
    expect(action?.id).toBe('linked-issue:github:EMD-123');
    expect(action?.kind).toBe('linked-issue');
    expect(action?.provider).toBe('github');
    expect(action?.issue).toBe(issue);
  });

  it('uses the issue provider and identifier in the id', () => {
    const action = buildLinkedIssueContextAction(
      makeIssue({ provider: 'linear', identifier: 'LIN-42' })
    );

    expect(action?.id).toBe('linked-issue:linear:LIN-42');
    expect(action?.provider).toBe('linear');
  });
});

describe('buildPromptLibraryContextActions', () => {
  it('builds one action per non-empty prompt', () => {
    const actions = buildPromptLibraryContextActions([
      { id: 'one', title: 'Security review', prompt: 'Check auth boundaries.' },
      { id: 'two', title: 'Empty', prompt: '   ' },
    ]);

    expect(actions).toHaveLength(1);
    expect(actions[0]?.id).toBe('prompt:one');
    expect(actions[0]?.kind).toBe('prompt');
    expect(actions[0]?.prompt).toEqual({
      id: 'one',
      title: 'Security review',
      prompt: 'Check auth boundaries.',
    });
  });

  it('returns an empty array when all prompts are blank', () => {
    const actions = buildPromptLibraryContextActions([{ id: 'x', title: 'X', prompt: '  ' }]);
    expect(actions).toHaveLength(0);
  });
});

describe('buildDraftCommentsContextAction', () => {
  it('returns null when the comments array is empty', () => {
    expect(buildDraftCommentsContextAction([])).toBeNull();
  });

  it('builds an action with commentCount and fileCount', () => {
    const comments = [
      makeDraftComment({ filePath: 'src/a.ts', lineNumber: 1 }),
      makeDraftComment({ filePath: 'src/a.ts', lineNumber: 5 }),
      makeDraftComment({ filePath: 'src/b.ts', lineNumber: 2 }),
    ];
    const action = buildDraftCommentsContextAction(comments);

    expect(action).not.toBeNull();
    expect(action?.id).toBe('draft-comments');
    expect(action?.kind).toBe('draft-comments');
    expect(action?.commentCount).toBe(3);
    expect(action?.fileCount).toBe(2);
    expect(action?.comments).toBe(comments);
  });

  it('counts each unique filePath as one file', () => {
    const comments = [
      makeDraftComment({ filePath: 'src/x.ts' }),
      makeDraftComment({ filePath: 'src/x.ts' }),
      makeDraftComment({ filePath: 'src/y.ts' }),
    ];
    const action = buildDraftCommentsContextAction(comments);

    expect(action?.fileCount).toBe(2);
  });
});

describe('buildTaskContextActions', () => {
  it('includes linked issue context, draft comments, then prompt library actions', () => {
    const comments = [makeDraftComment()];
    const actions = buildTaskContextActions(makeIssue(), comments, [
      { id: 'review-prompt', title: 'Review prompt', prompt: 'Review this worktree.' },
      { id: 'custom', title: 'Perf review', prompt: 'Look for slow paths.' },
    ]);

    expect(actions).toHaveLength(4);
    expect(actions[0]?.id).toBe('linked-issue:github:EMD-123');
    expect(actions[1]?.id).toBe('draft-comments');
    expect(actions[2]?.id).toBe('prompt:review-prompt');
    expect(actions[3]?.id).toBe('prompt:custom');
  });

  it('omits the linked issue action when issue is undefined', () => {
    const actions = buildTaskContextActions(
      undefined,
      [],
      [{ id: 'p', title: 'P', prompt: 'Do it.' }]
    );
    expect(actions).toHaveLength(1);
    expect(actions[0]?.kind).toBe('prompt');
  });

  it('omits the draft-comments action when comments array is empty', () => {
    const actions = buildTaskContextActions(makeIssue(), [], []);
    expect(actions).toHaveLength(1);
    expect(actions[0]?.kind).toBe('linked-issue');
  });
});
