import path from 'node:path';
import type { WatchEvent } from '#services/fs-watch/api';

export type RepoWatchEffects = {
  refs: boolean;
  remotes: boolean;
};

export type WorktreeWatchEffects = {
  status: boolean;
  head: boolean;
};

export type GitLayout = {
  gitCommonDir: string;
  worktrees: { id: string; gitDir: string; worktree: string }[];
};

export type GitWatchClassification = {
  repo: RepoWatchEffects;
  worktrees: Map<string, WorktreeWatchEffects>;
};

export function classifyGitWatchEvents(
  events: WatchEvent[],
  layout: GitLayout
): GitWatchClassification {
  const repo: RepoWatchEffects = { refs: false, remotes: false };
  const worktrees = new Map<string, WorktreeWatchEffects>();
  const gitCommonDir = normalize(layout.gitCommonDir);
  const normalizedWorktrees = layout.worktrees.map((worktree) => ({
    ...worktree,
    gitDir: normalize(worktree.gitDir),
    worktree: normalize(worktree.worktree),
  }));

  const addWorktreeEffect = (id: string, effect: keyof WorktreeWatchEffects) => {
    const current = worktrees.get(id) ?? { status: false, head: false };
    current[effect] = true;
    worktrees.set(id, current);
  };
  const addAllWorktreeEffects = (effects: Partial<WorktreeWatchEffects>) => {
    for (const worktree of normalizedWorktrees) {
      const current = worktrees.get(worktree.id) ?? { status: false, head: false };
      worktrees.set(worktree.id, {
        status: current.status || effects.status === true,
        head: current.head || effects.head === true,
      });
    }
  };

  for (const event of events) {
    const eventPath = normalize(event.path);
    const commonRel = relativeInside(gitCommonDir, eventPath);
    if (commonRel !== null) {
      classifyCommonGitPath(commonRel, repo);
      if (commonGitPathAffectsWorktreeHead(commonRel)) {
        addAllWorktreeEffects({
          status:
            commonRel.startsWith('refs/heads/') ||
            commonRel === 'HEAD' ||
            commonRel === 'packed-refs',
          head: true,
        });
      }
    }

    for (const worktree of normalizedWorktrees) {
      const gitRel = relativeInside(worktree.gitDir, eventPath);
      if (gitRel !== null) {
        if (gitRel === 'HEAD') {
          addWorktreeEffect(worktree.id, 'head');
          addWorktreeEffect(worktree.id, 'status');
        }
        if (gitRel === 'index') addWorktreeEffect(worktree.id, 'status');
      }

      const worktreeRel = relativeInside(worktree.worktree, eventPath);
      if (worktreeRel !== null && !isDotGitPath(worktreeRel)) {
        addWorktreeEffect(worktree.id, 'status');
      }
    }
  }

  return { repo, worktrees };
}

function classifyCommonGitPath(rel: string, repo: RepoWatchEffects): void {
  if (rel.startsWith('refs/heads/') || rel === 'HEAD') {
    repo.refs = true;
  }
  if (rel.startsWith('refs/remotes/') || rel.startsWith('refs/tags/')) {
    repo.refs = true;
  }
  if (rel === 'packed-refs') {
    repo.refs = true;
  }
  if (rel === 'config') {
    repo.refs = true;
    repo.remotes = true;
  }
}

function commonGitPathAffectsWorktreeHead(rel: string): boolean {
  return (
    rel.startsWith('refs/heads/') ||
    rel.startsWith('refs/remotes/') ||
    rel === 'HEAD' ||
    rel === 'config' ||
    rel === 'packed-refs'
  );
}

function relativeInside(root: string, child: string): string | null {
  const rel = path.relative(root, child).replace(/\\/g, '/');
  if (rel === '') return '';
  if (rel.startsWith('../') || rel === '..' || path.isAbsolute(rel)) return null;
  return rel;
}

function normalize(filePath: string): string {
  return path.resolve(filePath);
}

function isDotGitPath(rel: string): boolean {
  return rel === '.git' || rel.startsWith('.git/');
}
