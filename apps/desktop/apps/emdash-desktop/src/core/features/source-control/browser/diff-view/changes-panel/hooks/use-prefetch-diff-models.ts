import { useCallback, useEffect, useRef } from 'react';
import {
  openFileStore,
  type OpenFileLease,
} from '@core/features/editor/api/browser/open-file-store/open-file-store';
import { isBinaryForDiff } from '@core/features/editor/api/browser/renderers/fileKind';
import { useWorkspace } from '@core/features/workbench/api/browser/task-composition-context';
import type { GitRef } from '@core/primitives/git/api';
import { diffSideSpecs, specToFacet, workspaceDiffFileRef } from '../../stores/diff-facets';

/**
 * Returns a stable callback that warms OpenFileStore interest on hover so
 * that when the user clicks to open a diff, both sides' content is already
 * loaded. Plain interest warming (spec §9): the same acquire the diff views
 * use, held until the section unmounts; the store's linger covers the
 * hand-off to the opened diff's own leases. No special code path, no LRU.
 *
 * Pass `modifiedRef` for 'git'/'pr' groups to pre-warm a fixed modified-side
 * ref instead of HEAD.
 */
export function usePrefetchDiffModels(
  group: 'disk' | 'staged' | 'git' | 'pr',
  originalRef: GitRef,
  modifiedRef?: GitRef
) {
  const workspace = useWorkspace();
  const leasesRef = useRef(new Map<string, OpenFileLease[]>());

  useEffect(() => {
    const leases = leasesRef.current;
    return () => {
      for (const held of leases.values()) {
        for (const lease of held) lease.release();
      }
      leases.clear();
    };
  }, [workspace.workspaceId]);

  return useCallback(
    (filePath: string) => {
      if (leasesRef.current.has(filePath)) return;
      if (isBinaryForDiff(filePath)) return;
      const fileRef = workspaceDiffFileRef(workspace.path, workspace.sshConnectionId, filePath);
      if (!fileRef) return;
      const specs = diffSideSpecs({ group, originalRef, modifiedRef });
      leasesRef.current.set(filePath, [
        openFileStore.acquire(fileRef, specToFacet(specs.original)),
        openFileStore.acquire(fileRef, specToFacet(specs.modified)),
      ]);
    },
    [workspace.path, workspace.sshConnectionId, group, originalRef, modifiedRef]
  );
}
