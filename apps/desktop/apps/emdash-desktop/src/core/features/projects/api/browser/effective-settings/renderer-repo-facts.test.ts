import {
  localBranchRefSchema,
  remoteBranchRefSchema,
  type GitBranch,
  type GitRemote,
} from '@emdash/core/runtimes/git/api';
import { describe, expect, it } from 'vitest';
import { buildRendererRepoFacts } from './renderer-repo-facts';

const origin: GitRemote = { name: 'origin', url: 'git@github.com:example/repo.git' };
const fork: GitRemote = { name: 'fork', url: 'https://ghe.example.com/me/repo.git' };

const branches: GitBranch[] = [
  { type: 'local', ref: localBranchRefSchema.parse('refs/heads/main'), oid: 'a' },
  { type: 'local', ref: localBranchRefSchema.parse('refs/heads/feature/x'), oid: 'b' },
  {
    type: 'remote',
    ref: remoteBranchRefSchema.parse('refs/remotes/origin/main'),
    remote: origin,
    oid: 'c',
  },
  {
    type: 'remote',
    ref: remoteBranchRefSchema.parse('refs/remotes/origin/develop'),
    remote: origin,
    oid: 'd',
  },
  {
    type: 'remote',
    ref: remoteBranchRefSchema.parse('refs/remotes/fork/main'),
    remote: fork,
    oid: 'e',
  },
];

describe('buildRendererRepoFacts', () => {
  it('maps the repository live model to resolver repo facts', () => {
    const facts = buildRendererRepoFacts({
      remotes: [origin, fork],
      branches,
      remoteHeads: [
        { remote: 'origin', ref: remoteBranchRefSchema.parse('refs/remotes/origin/develop') },
        { remote: 'fork', ref: remoteBranchRefSchema.parse('refs/remotes/fork/main') },
      ],
    });

    expect(facts).toEqual({
      remotes: [
        {
          name: 'origin',
          host: 'github.com',
          headBranch: 'develop',
          branches: ['main', 'develop'],
        },
        {
          name: 'fork',
          host: 'ghe.example.com',
          headBranch: 'main',
          branches: ['main'],
        },
      ],
      localBranches: ['main', 'feature/x'],
    });
  });

  it('degrades to null head branches when the remote HEAD is unknown', () => {
    const facts = buildRendererRepoFacts({ remotes: [origin], branches, remoteHeads: [] });

    expect(facts.remotes[0].headBranch).toBeNull();
  });

  it('produces empty facts for a repository without remotes or refs', () => {
    expect(buildRendererRepoFacts({ remotes: [], branches: [], remoteHeads: [] })).toEqual({
      remotes: [],
      localBranches: [],
    });
  });
});
