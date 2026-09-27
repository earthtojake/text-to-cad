import { useEffect, useMemo, useState } from "react";
import {
  editingPreviewEntry, initialEditingPreview, reduceEditingPreview,
} from "../../../workbench/editingPreview.js";
import { observeEditingPreview } from "../../../workbench/editingPreviewFeed.js";

export function useEditingPreview(file, { enabled, catalogEntry, client } = {}) {
  const [snapshot, setSnapshot] = useState(() => ({ file: "", state: initialEditingPreview() }));
  useEffect(() => {
    if (!enabled || !file) return undefined;
    // A poll that changes nothing, a failed one included, keeps the snapshot: the surface re-renders
    // only for news, not once per poll while the feed is down.
    const apply = next => setSnapshot(previous => {
      const before = previous.file === file ? previous.state : initialEditingPreview();
      const state = reduceEditingPreview(before, next);
      return previous.file === file && JSON.stringify(before) === JSON.stringify(state)
        ? previous : { file, state };
    });
    return observeEditingPreview(file, apply, error => apply({ error: error.message }), { client });
  }, [file, enabled, client]);
  const state = useMemo(() => enabled && snapshot.file === file
    ? snapshot.state : initialEditingPreview(), [enabled, file, snapshot]);
  const entry = useMemo(() => editingPreviewEntry(state, catalogEntry), [
    state.preview, state.revision, state.output, state.file,
    state.previewUnavailable,
    state.saved?.tree, state.saved?.documentHash,
    state.retainedSaved?.tree, state.retainedSaved?.documentHash, catalogEntry,
  ]);
  return { entry, state };
}
