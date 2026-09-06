import { encodeResourceUri } from '@emdash/core/primitives/path/api';
import { describe, expect, it } from 'vitest';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import { commitRef, HEAD_REF, STAGED_REF } from '@core/primitives/git/api';
import { diffFacetSpecKey, diffSideSpecs, specToFacet, workspaceDiffFileRef } from './diff-facets';

describe('diffSideSpecs', () => {
  it('maps unstaged (disk) diffs to index snapshot vs the editable buffer', () => {
    const specs = diffSideSpecs({ group: 'disk', originalRef: HEAD_REF });
    expect(specs.original).toEqual({ kind: 'git', ref: STAGED_REF });
    expect(specs.modified).toEqual({ kind: 'buffer' });
  });

  it('maps staged diffs to HEAD snapshot vs index snapshot', () => {
    const specs = diffSideSpecs({ group: 'staged', originalRef: HEAD_REF });
    expect(specs.original).toEqual({ kind: 'git', ref: HEAD_REF });
    expect(specs.modified).toEqual({ kind: 'git', ref: STAGED_REF });
  });

  it('maps commit-range diffs to two git snapshots at the given refs', () => {
    const base = commitRef('aaa111');
    const head = commitRef('bbb222');
    const specs = diffSideSpecs({ group: 'git', originalRef: base, modifiedRef: head });
    expect(specs.original).toEqual({ kind: 'git', ref: base });
    expect(specs.modified).toEqual({ kind: 'git', ref: head });
  });

  it('defaults the modified side of git/pr diffs to HEAD when no ref is given', () => {
    const base = commitRef('aaa111');
    for (const group of ['git', 'pr'] as const) {
      const specs = diffSideSpecs({ group, originalRef: base });
      expect(specs.modified).toEqual({ kind: 'git', ref: HEAD_REF });
    }
  });

  it('keys merge-base range sides distinctly so both facets coexist on one entry', () => {
    const specs = diffSideSpecs({
      group: 'pr',
      originalRef: commitRef('aaa111'),
      modifiedRef: commitRef('bbb222'),
    });
    expect(diffFacetSpecKey(specs.original)).not.toBe(diffFacetSpecKey(specs.modified));
  });

  it('round-trips specs into store facets', () => {
    expect(specToFacet({ kind: 'buffer' })).toEqual({ kind: 'buffer' });
    expect(specToFacet({ kind: 'git', ref: STAGED_REF })).toEqual({
      kind: 'git',
      ref: STAGED_REF,
    });
  });
});

describe('workspaceDiffFileRef', () => {
  it('resolves a checkout-relative path against the workspace root', () => {
    const ref = workspaceDiffFileRef('/repo', undefined, 'src/index.ts');
    expect(ref).not.toBeNull();
    expect(encodeResourceUri(ref!)).toBe(
      encodeResourceUri(hostFileRefFromNativePath('/repo/src/index.ts'))
    );
  });

  it('carries the remote host into the identity for ssh workspaces', () => {
    const ref = workspaceDiffFileRef('/repo', 'ssh-1', 'src/index.ts');
    expect(ref?.host).toEqual({ type: 'remote', id: 'ssh-1' });
  });

  it('returns null instead of throwing for unresolvable paths', () => {
    expect(workspaceDiffFileRef('', undefined, '')).toBeNull();
  });
});
