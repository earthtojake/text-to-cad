import type { HostFileRef } from '@emdash/core/primitives/path/api';
import type { Facet } from '@core/features/editor/api/browser/open-file-store/facet-handle';
import { facetSlotKey } from '@core/features/editor/api/browser/open-file-store/facet-handle';
import { resolveWorkspacePath } from '@core/features/workspaces/api/browser/workspace-path';
import { hostFileRefFromNativePath } from '@core/primitives/desktop-runtime/api';
import { HEAD_REF, STAGED_REF, type GitRef } from '@core/primitives/git/api';

/**
 * Which OpenFileStore facet one side of a diff reads (spec §6): the old side
 * is a git snapshot at the relevant ref; the new side is the editable buffer
 * for working-tree diffs or another git snapshot for staged/range diffs.
 * Added and deleted files need no special spec — a git side whose ref does
 * not contain the path reports `error(not-found)` and renders empty, and a
 * buffer side for a deleted file reports not-found/orphaned and renders
 * empty (see the sticky diff editor's side resolution).
 */
export type DiffFacetSpec = { kind: 'git'; ref: GitRef } | { kind: 'buffer' };

export interface DiffSideSpecs {
  original: DiffFacetSpec;
  modified: DiffFacetSpec;
}

export interface DiffSpecArgs {
  group: 'disk' | 'staged' | 'git' | 'pr';
  originalRef: GitRef;
  modifiedRef?: GitRef;
}

/**
 * Derives both sides' facet specs from the diff group — the mapping harvested
 * from the legacy registry-based renderers:
 *
 * - `disk` (unstaged): index snapshot vs the working tree's editable buffer
 * - `staged`: HEAD snapshot vs index snapshot
 * - `git` / `pr` (commit and merge-base ranges): two git snapshots, which
 *   coexist as separate facets on one entry
 */
export function diffSideSpecs({ group, originalRef, modifiedRef }: DiffSpecArgs): DiffSideSpecs {
  switch (group) {
    case 'disk':
      return { original: { kind: 'git', ref: STAGED_REF }, modified: { kind: 'buffer' } };
    case 'staged':
      return {
        original: { kind: 'git', ref: HEAD_REF },
        modified: { kind: 'git', ref: STAGED_REF },
      };
    case 'git':
    case 'pr':
      return {
        original: { kind: 'git', ref: originalRef },
        modified: { kind: 'git', ref: modifiedRef ?? HEAD_REF },
      };
  }
}

export function specToFacet(spec: DiffFacetSpec): Facet {
  return spec.kind === 'git' ? { kind: 'git', ref: spec.ref } : { kind: 'buffer' };
}

/** Stable identity of a spec, for effect keying. */
export function diffFacetSpecKey(spec: DiffFacetSpec): string {
  return facetSlotKey(specToFacet(spec));
}

/**
 * Resolves a checkout-relative diff path to the file's identity, exactly like
 * the file-tab cutover: workspace→root resolution happens here at the
 * renderer edge (spec §2), and the workspace binding carries the host.
 * Returns null for paths that cannot form a well-formed identity — those
 * sides render nothing rather than throwing.
 */
export function workspaceDiffFileRef(
  workspacePath: string,
  sshConnectionId: string | undefined,
  filePath: string
): HostFileRef | null {
  try {
    return hostFileRefFromNativePath(
      resolveWorkspacePath(workspacePath, filePath),
      sshConnectionId
    );
  } catch {
    return null;
  }
}
