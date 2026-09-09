import {
  decodeResourceUri,
  encodeResourceUri,
  type HostFileRef,
} from '@emdash/core/primitives/path/api';
import { useEffect, useMemo, useState } from 'react';
import { encodeFacetUri } from '@core/features/editor/api/browser/facet-binder/facet-uri';
import type { Facet } from '@core/features/editor/api/browser/open-file-store/facet-handle';
import {
  openFileStore,
  type OpenFileEntry,
} from '@core/features/editor/api/browser/open-file-store/open-file-store';
import type { DiffSideModel } from '@core/features/editor/contributions/browser/monaco/sticky-diff-editor';
import type { GitRef } from '@core/primitives/git/api';
import {
  diffFacetSpecKey,
  diffSideSpecs,
  specToFacet,
  workspaceDiffFileRef,
} from '../stores/diff-facets';

export interface DiffFacetsArgs {
  workspacePath: string;
  sshConnectionId: string | undefined;
  /** Checkout-relative path of the diffed file. */
  filePath: string;
  group: 'disk' | 'staged' | 'git' | 'pr';
  originalRef: GitRef;
  modifiedRef?: GitRef;
  /** False skips acquisition entirely (binary files, collapsed slots). */
  enabled?: boolean;
}

export interface DiffFacetSides {
  original: DiffSideModel | null;
  modified: DiffSideModel | null;
}

const EMPTY_SIDES: DiffFacetSides = { original: null, modified: null };

/**
 * Holds OpenFileStore leases for both sides of one diff (spec §6, Stage 3):
 * maps the diff group to facet specs, resolves the file's identity at the
 * renderer edge, and acquires one lease per side for the component's
 * lifetime. Releasing on side identity change or unmount is safe across
 * quick flips — the store's linger keeps the content warm.
 *
 * Both sides key on the same path: the diff data carries a single path per
 * change (renames do not surface the old path), matching the legacy
 * registry-based renderers.
 */
export function useDiffFacets({
  workspacePath,
  sshConnectionId,
  filePath,
  group,
  originalRef,
  modifiedRef,
  enabled = true,
}: DiffFacetsArgs): DiffFacetSides {
  const [sides, setSides] = useState<DiffFacetSides>(EMPTY_SIDES);

  const fileRef = useMemo(
    () => workspaceDiffFileRef(workspacePath, sshConnectionId, filePath),
    [workspacePath, sshConnectionId, filePath]
  );
  const specs = useMemo(
    () => diffSideSpecs({ group, originalRef, modifiedRef }),
    [group, originalRef, modifiedRef]
  );

  // Identity keys: re-acquire only when the resolved file or a side's facet
  // actually changes, not when the (observable) ref objects are replaced by
  // equal values.
  const refKey = fileRef ? encodeResourceUri(fileRef) : null;
  const originalKey = diffFacetSpecKey(specs.original);
  const modifiedKey = diffFacetSpecKey(specs.modified);

  useEffect(() => {
    if (!enabled || !fileRef) {
      setSides(EMPTY_SIDES);
      return;
    }
    const originalFacet = specToFacet(specs.original);
    const modifiedFacet = specToFacet(specs.modified);
    const originalLease = openFileStore.acquire(fileRef, originalFacet);
    const modifiedLease = openFileStore.acquire(fileRef, modifiedFacet);
    setSides({
      original: sideModel(originalLease.entry, originalFacet, fileRef),
      modified: sideModel(modifiedLease.entry, modifiedFacet, fileRef),
    });
    return () => {
      originalLease.release();
      modifiedLease.release();
    };
    // Keyed by stable identity strings; fileRef/specs are memoized from them.
    // oxlint-disable-next-line react/exhaustive-deps
  }, [enabled, refKey, originalKey, modifiedKey]);

  return sides;
}

/**
 * The binder derives Monaco URIs from the entry's canonical (first-seen)
 * spelling, so the side's URI must too — a diff on a spelling that shares an
 * already-open entry would otherwise miss the binder's models.
 */
function sideModel(entry: OpenFileEntry, facet: Facet, fallbackRef: HostFileRef): DiffSideModel {
  const decoded = decodeResourceUri(entry.uri);
  const ref = decoded.success ? decoded.data : fallbackRef;
  return { kind: 'facet', entry, facet, uri: encodeFacetUri(ref, facet) };
}
