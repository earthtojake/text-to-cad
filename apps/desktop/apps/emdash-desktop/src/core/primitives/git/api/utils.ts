import type { GitBranchRef, GitObjectRef, GitRemote, MergeBaseRange } from './types';
import type { GitRef } from './types';

export function toRangeString(range: MergeBaseRange): string {
  return `${toRefString(range.base)}...${toRefString(range.head)}`;
}

export function mergeBaseRange(base: GitObjectRef, head: GitObjectRef): MergeBaseRange {
  return { base, head };
}

export function toRefString(ref: GitObjectRef): string {
  switch (ref.kind) {
    case 'branch':
      return ref.branch.type === 'remote'
        ? `${ref.branch.remote.name}/${ref.branch.branch}`
        : ref.branch.branch;
    case 'commit':
      return ref.sha;
    case 'tag':
      return ref.name;
  }
}

export function gitRefToString(ref: GitRef): string {
  if (ref.kind === 'head') return 'HEAD';
  if (ref.kind === 'staged') return 'STAGED';
  if (ref.kind === 'unstaged') return 'UNSTAGED';
  return toRefString(ref);
}

export function refsEqual(a: GitRef, b: GitRef): boolean {
  if (a.kind !== b.kind) return false;
  switch (a.kind) {
    case 'head':
    case 'staged':
    case 'unstaged':
      return true;
    case 'branch': {
      const ab = a.branch;
      const bb = (b as typeof a).branch;
      if (ab.type !== bb.type) return false;
      if (ab.type === 'remote' && bb.type === 'remote') {
        return ab.remote.name === bb.remote.name && ab.branch === bb.branch;
      }
      return ab.branch === bb.branch;
    }
    case 'commit':
      return a.sha === (b as typeof a).sha;
    case 'tag':
      return a.name === (b as typeof a).name;
  }
}

export function remoteRef(remote: GitRemote | string, branch: string): GitObjectRef {
  const value: GitRemote = typeof remote === 'string' ? { name: remote, url: '' } : remote;
  return { kind: 'branch', branch: { type: 'remote', branch, remote: value } };
}

export function localRef(branch: string): GitObjectRef {
  return { kind: 'branch', branch: { type: 'local', branch } };
}

export function commitRef(sha: string): GitObjectRef {
  return { kind: 'commit', sha };
}

export function bareRefName(ref: string): string {
  const slash = ref.indexOf('/');
  return slash !== -1 ? ref.slice(slash + 1) : ref;
}

type BaseRefResolutionArgs = {
  detectedBaseRef: string;
  gitDefaultBranch?: string;
  branches: ReadonlyArray<GitBranchRef>;
};

function findRemoteBranch<TBranch extends GitBranchRef>(
  branches: ReadonlyArray<TBranch>,
  branchName: string,
  remoteName: string
): TBranch | undefined {
  return branches.find(
    (b) => b.type === 'remote' && b.branch === branchName && b.remote.name === remoteName
  );
}

export function remoteNameFromQualifiedRef(ref: string): string | undefined {
  const trimmed = ref.trim();
  const slash = trimmed.indexOf('/');
  if (slash <= 0) return undefined;
  return trimmed.slice(0, slash);
}

export function resolveBaseRefFromRemoteDefault(args: BaseRefResolutionArgs): string {
  const remoteName = remoteNameFromQualifiedRef(args.detectedBaseRef);
  if (!remoteName) return args.detectedBaseRef;

  const defaultBranch = args.gitDefaultBranch?.trim();
  if (!defaultBranch) return args.detectedBaseRef;

  const defaultBranchName = bareRefName(defaultBranch);
  const remoteDefault = findRemoteBranch(args.branches, defaultBranchName, remoteName);
  return remoteDefault ? `${remoteName}/${defaultBranchName}` : args.detectedBaseRef;
}
