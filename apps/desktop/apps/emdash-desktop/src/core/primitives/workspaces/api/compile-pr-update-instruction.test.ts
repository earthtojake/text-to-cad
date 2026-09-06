import { describe, expect, it } from 'vitest';
import { compilePrUpdateInstruction } from './compile-pr-update-instruction';

// The manual "Update now" instruction compiler (pr-workspace-model spec, Staleness):
// per-case source refs matching the createWorktree presets, compiled purely from the
// associated PR and the project's base remote — never from workspace config or host
// record fields, so pre-model workspaces compile identically.

const REPO_URL = 'https://github.com/acme/app';

function prFacts(overrides: Partial<Parameters<typeof compilePrUpdateInstruction>[0]> = {}) {
  return {
    identifier: '#42',
    headRefName: 'feature/login',
    repositoryUrl: REPO_URL,
    headRepositoryUrl: REPO_URL,
    ...overrides,
  };
}

describe('compilePrUpdateInstruction', () => {
  it('same-repo PRs update from the real head branch on the base remote', () => {
    expect(compilePrUpdateInstruction(prFacts(), { baseRemote: 'origin' })).toEqual({
      remote: 'origin',
      sourceRef: 'refs/heads/feature/login',
    });
  });

  it('fork PRs update from the read-only PR ref on the base remote', () => {
    const pr = prFacts({ headRepositoryUrl: 'https://github.com/fork/app' });
    expect(compilePrUpdateInstruction(pr, { baseRemote: 'origin' })).toEqual({
      remote: 'origin',
      sourceRef: 'refs/pull/42/head',
    });
  });

  it('respects a non-default configured base remote', () => {
    expect(compilePrUpdateInstruction(prFacts(), { baseRemote: 'upstream' })).toEqual({
      remote: 'upstream',
      sourceRef: 'refs/heads/feature/login',
    });
  });

  it('compiles purely from the associated PR — pre-model workspaces need nothing else', () => {
    // Nothing here comes from a workspace config or a host record: the same cached
    // PR facts old branch-matched associations produce compile the same instruction.
    const instruction = compilePrUpdateInstruction(
      prFacts({ identifier: '7', headRefName: 'fix/crash' }),
      { baseRemote: 'origin' }
    );
    expect(instruction).toEqual({ remote: 'origin', sourceRef: 'refs/heads/fix/crash' });
  });

  it('returns null when the PR number cannot be determined', () => {
    expect(
      compilePrUpdateInstruction(prFacts({ identifier: null }), { baseRemote: 'origin' })
    ).toBe(null);
    expect(
      compilePrUpdateInstruction(prFacts({ identifier: 'draft' }), { baseRemote: 'origin' })
    ).toBe(null);
  });
});
