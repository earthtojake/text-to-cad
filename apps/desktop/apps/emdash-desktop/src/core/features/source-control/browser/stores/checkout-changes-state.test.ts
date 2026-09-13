import type { CheckoutStatusState, GitChange, GitStatusCode } from '@emdash/core/runtimes/git/api';
import { describe, expect, it } from 'vitest';
import { portablePath } from '@core/primitives/desktop-runtime/api';
import {
  projectCheckoutChanges,
  reduceStageAll,
  reduceStageFiles,
  reduceUnstageFiles,
  type CheckoutChangesState,
} from './checkout-changes-state';

describe('checkout changes state', () => {
  it('derives side membership from status and enriches it with side-specific diff metadata', () => {
    const status = okStatus({
      'partial.ts': {
        index: 'added',
        worktree: 'modified',
      },
      'staged.ts': {
        index: 'deleted',
        worktree: 'unmodified',
      },
    });
    const metadata: CheckoutChangesState = {
      staged: [change('partial.ts', 'added', 2), change('staged.ts', 'deleted', 0, 3)],
      unstaged: [change('partial.ts', 'modified', 1, 1)],
    };

    expect(projectCheckoutChanges(status, metadata)).toEqual(metadata);
  });

  it('uses status as the authority for membership', () => {
    const metadata: CheckoutChangesState = {
      staged: [change('stale.ts', 'modified', 3)],
      unstaged: [change('stale.ts', 'modified', 3)],
    };

    expect(projectCheckoutChanges(okStatus({}), metadata)).toEqual({ staged: [], unstaged: [] });
  });

  it('projects untracked files missing from git diff as unstaged additions', () => {
    const projected = projectCheckoutChanges(
      okStatus({
        'new.ts': {
          index: 'untracked',
          worktree: 'untracked',
        },
      }),
      { staged: [], unstaged: [] }
    );

    expect(projected).toEqual({
      staged: [],
      unstaged: [change('new.ts', 'added', 0, 0)],
    });
  });

  it('moves only the selected side of a partially staged file', () => {
    const changes: CheckoutChangesState = {
      staged: [change('partial.ts', 'added', 2)],
      unstaged: [change('partial.ts', 'modified', 1, 1), change('other.ts')],
    };

    reduceStageFiles(changes, { paths: ['partial.ts'] });
    expect(changes).toEqual({
      staged: [change('partial.ts', 'modified', 1, 1)],
      unstaged: [change('other.ts')],
    });

    reduceUnstageFiles(changes, { paths: ['partial.ts'] });
    expect(changes).toEqual({
      staged: [],
      unstaged: [change('other.ts'), change('partial.ts', 'modified', 1, 1)],
    });
  });

  it('stages all files with one entry per path', () => {
    const changes: CheckoutChangesState = {
      staged: [change('partial.ts', 'added', 2)],
      unstaged: [change('partial.ts', 'modified', 1, 1), change('other.ts')],
    };

    reduceStageAll(changes);

    expect(changes).toEqual({
      staged: [change('partial.ts', 'modified', 1, 1), change('other.ts')],
      unstaged: [],
    });
  });
});

function change(
  path: string,
  status: GitChange['status'] = 'modified',
  additions = 1,
  deletions = 0
): GitChange {
  return { path: portablePath(path), status, additions, deletions };
}

function okStatus(
  entries: Record<
    string,
    {
      index: GitStatusCode;
      worktree: GitStatusCode;
    }
  >
): CheckoutStatusState {
  const statusEntries: Extract<CheckoutStatusState, { kind: 'ok' }>['entries'] = {};
  for (const [path, entry] of Object.entries(entries)) {
    const portable = portablePath(path);
    statusEntries[portable] = { path: portable, ...entry, isConflicted: false };
  }
  return {
    kind: 'ok',
    entries: statusEntries,
    summary: { staged: 0, unstaged: 0, conflicted: 0, untracked: 0 },
    operation: 'none',
  };
}
