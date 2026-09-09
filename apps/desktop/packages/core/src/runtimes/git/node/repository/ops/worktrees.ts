import type { HostAbsolutePath } from '#primitives/path/api';
import {
  localBranchRefSchema,
  type WorktreeHeadSummary,
  type WorktreeSummary,
} from '#runtimes/git/api';

const UNBORN_OID = /^0+$/;

export function parseWorktreeList(
  stdout: string,
  parsePath: (filePath: string) => HostAbsolutePath
): WorktreeSummary[] {
  const worktrees: WorktreeSummary[] = [];
  let current: Partial<{
    path: string;
    oid: string;
    branch: string;
    detached: boolean;
    locked: boolean;
    prunable: boolean;
    prunableReason: string;
  }> = {};

  const flush = () => {
    if (!current.path) return;
    worktrees.push({
      worktreePath: parsePath(current.path),
      isMain: worktrees.length === 0,
      head: toWorktreeHead(current),
      ...(current.locked ? { locked: true } : {}),
      ...(current.prunable ? { prunable: true } : {}),
      ...(current.prunableReason ? { prunableReason: current.prunableReason } : {}),
    });
    current = {};
  };

  for (const line of stdout.split('\n')) {
    if (line === '') {
      flush();
      continue;
    }
    if (line.startsWith('worktree ')) current.path = line.slice('worktree '.length);
    else if (line.startsWith('HEAD ')) current.oid = line.slice('HEAD '.length);
    else if (line.startsWith('branch ')) current.branch = line.slice('branch '.length);
    else if (line === 'detached') current.detached = true;
    else if (line === 'locked' || line.startsWith('locked ')) current.locked = true;
    else if (line === 'prunable' || line.startsWith('prunable ')) {
      current.prunable = true;
      const reason = line.slice('prunable'.length).trim();
      if (reason) current.prunableReason = reason;
    }
  }
  flush();

  return worktrees;
}

export function toWorktreeHead(entry: {
  oid?: string;
  branch?: string;
  detached?: boolean;
}): WorktreeHeadSummary {
  const oid = entry.oid ?? '';
  const ref = entry.branch ? localBranchRefSchema.parse(entry.branch) : null;
  if (ref && (!oid || UNBORN_OID.test(oid))) {
    return { kind: 'unborn', ref };
  }
  if (ref) return { kind: 'branch', ref };
  return { kind: 'detached' };
}
