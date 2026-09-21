import { useEffect, useMemo, useState } from "react";
import {
  editingPreviewEntry, initialEditingPreview, reduceEditingPreview,
} from "../../../workbench/editingPreview.js";
import { observeEditingPreview } from "../../../workbench/editingPreviewFeed.js";

export function useEditingPreview(file, { enabled, catalogEntry, client } = {}) {
  const [snapshot, setSnapshot] = useState(() => ({ file: "", state: initialEditingPreview() }));
  useEffect(() => {
    if (!enabled || !file) return undefined;
    return observeEditingPreview(file, next => {
      setSnapshot(previous => {
        const before = previous.file === file ? previous.state : initialEditingPreview();
        const state = reduceEditingPreview(before, next);
        return previous.file === file && JSON.stringify(before) === JSON.stringify(state)
          ? previous : { file, state };
      });
    }, error => {
      setSnapshot(previous => ({ file, state: reduceEditingPreview(
        previous.file === file ? previous.state : initialEditingPreview(), { error: error.message },
      ) }));
    }, { client });
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
