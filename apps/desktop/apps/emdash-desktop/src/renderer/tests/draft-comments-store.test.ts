import { beforeEach, describe, expect, it, vi } from 'vitest';
import { DraftCommentsStore } from '@core/features/source-control/api/browser/diff-view/stores/draft-comments-store';
import {
  getDraftCommentTargetKey,
  type DraftCommentTarget,
} from '@core/primitives/line-comments/api';

const diskTarget: DraftCommentTarget = {
  kind: 'working-tree',
  group: 'disk',
  path: 'src/example.ts',
};

const stagedTarget: DraftCommentTarget = {
  kind: 'working-tree',
  group: 'staged',
  path: 'src/example.ts',
};

describe('DraftCommentsStore', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    const ids = [
      '11111111-1111-1111-1111-111111111111',
      '22222222-2222-2222-2222-222222222222',
    ] as const;
    let index = 0;
    vi.spyOn(globalThis.crypto, 'randomUUID').mockImplementation(
      () => ids[index++] ?? '33333333-3333-3333-3333-333333333333'
    );
  });

  it('consumes the current formatted comments and clears the store', () => {
    const store = new DraftCommentsStore('task-1');

    store.addComment({
      target: diskTarget,
      lineNumber: 12,
      lineContent: 'const value = 1;',
      content: 'Rename this to be clearer.',
    });

    const formatted = store.consumeAll();

    expect(formatted).toContain('<user_comments>');
    expect(formatted).toContain('src/example.ts');
    expect(formatted).toContain('line="12"');
    expect(formatted).toContain('Rename this to be clearer.');
    expect(store.count).toBe(0);
    expect(store.comments).toEqual([]);
    expect(store.formattedForAgent).toBe('');
  });

  it('filters comments by exact target, not file path', () => {
    const store = new DraftCommentsStore('task-1');

    store.addComment({
      target: diskTarget,
      lineNumber: 12,
      content: 'Working tree comment.',
    });
    store.addComment({
      target: stagedTarget,
      lineNumber: 12,
      content: 'Staged comment.',
    });

    const diskComments = store.getCommentsForTarget(getDraftCommentTargetKey(diskTarget));
    const stagedComments = store.getCommentsForTarget(getDraftCommentTargetKey(stagedTarget));

    expect(diskComments).toHaveLength(1);
    expect(diskComments[0]?.content).toBe('Working tree comment.');
    expect(stagedComments).toHaveLength(1);
    expect(stagedComments[0]?.content).toBe('Staged comment.');
  });
});
