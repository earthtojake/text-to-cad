import {
  localBranchRefSchema,
  remoteBranchRefSchema,
  tagRefSchema,
  type GitBranch,
  type GitRefsState,
  type GitRemote,
  type GitRemoteHead,
  type GitTag,
} from '#runtimes/git/api';
import type { BoundExec } from '#services/exec/api';

const FIELD_SEPARATOR = '\u0000';

export async function computeRefsState(
  exec: BoundExec,
  remotes: GitRemote[]
): Promise<GitRefsState> {
  const [{ branches, remoteHeads }, tags] = await Promise.all([
    computeBranches(exec, remotes),
    computeTags(exec),
  ]);
  return { branches, tags, remoteHeads };
}

async function computeBranches(
  exec: BoundExec,
  remotes: GitRemote[]
): Promise<{ branches: GitBranch[]; remoteHeads: GitRemoteHead[] }> {
  const remoteByName = new Map(remotes.map((remote) => [remote.name, remote]));
  const remoteNames = [...remoteByName.keys()].sort((a, b) => b.length - a.length);
  const { stdout } = await exec.exec([
    'branch',
    '-a',
    '--format=%(refname)%00%(upstream:remotename)%00%(upstream:track)%00%(objectname)%00%(symref)',
  ]);
  const branches: GitBranch[] = [];
  const remoteHeads: GitRemoteHead[] = [];

  for (const line of stdout.trim().split('\n').filter(Boolean)) {
    const [fullRef, upstreamRemote, upstreamTrack, oid, symref] = line.split(FIELD_SEPARATOR);
    if (!fullRef || !oid) continue;
    if (fullRef.startsWith('refs/remotes/')) {
      const remoteName = remoteNames.find((name) => fullRef.startsWith(`refs/remotes/${name}/`));
      if (!remoteName) continue;
      const remote = remoteByName.get(remoteName);
      if (!remote) continue;
      const branchName = fullRef.slice(`refs/remotes/${remoteName}/`.length);
      if (branchName === 'HEAD') {
        // The remote HEAD symbolic ref: `%(symref)` carries its target
        // (`refs/remotes/<remote>/<branch>`) — a free local read.
        const targetPrefix = `refs/remotes/${remoteName}/`;
        if (symref?.startsWith(targetPrefix)) {
          remoteHeads.push({ remote: remoteName, ref: remoteBranchRefSchema.parse(symref) });
        }
        continue;
      }
      branches.push({
        type: 'remote',
        ref: remoteBranchRefSchema.parse(fullRef),
        remote,
        oid,
      });
      continue;
    }

    if (!fullRef.startsWith('refs/heads/')) continue;
    const branch: GitBranch = { type: 'local', ref: localBranchRefSchema.parse(fullRef), oid };
    if (upstreamRemote && upstreamRemote !== '.') {
      branch.remote = remoteByName.get(upstreamRemote) ?? { name: upstreamRemote, url: '' };
    }
    const divergence = parseDivergence(upstreamTrack ?? '');
    if (divergence) branch.divergence = divergence;
    branches.push(branch);
  }

  return { branches, remoteHeads };
}

async function computeTags(exec: BoundExec): Promise<GitTag[]> {
  const { stdout } = await exec.exec([
    'for-each-ref',
    'refs/tags',
    '--format=%(refname)%00%(objectname)%00%(*objectname)%00%(contents:subject)',
  ]);
  const tags: GitTag[] = [];

  for (const line of stdout.split('\n').filter(Boolean)) {
    const [fullName, oid, peeledOid, subject] = line.split(FIELD_SEPARATOR);
    if (!fullName?.startsWith('refs/tags/') || !oid) continue;
    const tag: GitTag = { ref: tagRefSchema.parse(fullName), oid: peeledOid || oid };
    if (subject) tag.message = subject;
    tags.push(tag);
  }

  return tags;
}

function parseDivergence(upstreamTrack: string): { ahead: number; behind: number } | undefined {
  if (!upstreamTrack) return undefined;
  const ahead = /ahead (\d+)/.exec(upstreamTrack)?.[1];
  const behind = /behind (\d+)/.exec(upstreamTrack)?.[1];
  if (!ahead && !behind) return undefined;
  return {
    ahead: ahead ? Number.parseInt(ahead, 10) : 0,
    behind: behind ? Number.parseInt(behind, 10) : 0,
  };
}
