import { useEffect, useMemo, useState } from "react";
import { initialEditingPreview, reduceEditingPreview } from "../../../workbench/editingPreview.js";
import { observeEditingPreview } from "../../../workbench/editingPreviewFeed.js";

// The build feed's state for `file`: its status, and the preview revision it names, which
// `usePreviewRevision` turns into the entry the view draws until the saved file replaces it. When a
// build writes the file (`saved`, the feed's own event: a build records its result and writes the
// file after), when it finishes, or when the file moves past one, the catalog is read at once, so
// the saved file replaces the one on screen without waiting for the catalog's next poll.
export function useEditingPreview(file, { enabled, client } = {}) {
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
  const settled = state.superseded === true || state.state === "done";
  const written = state.saved?.documentHash || "";
  useEffect(() => {
    if ((settled || written) && file) void client?.refresh?.({ file, markRefreshing: false })?.catch?.(() => {});
  }, [settled, written, file, client, state.revision]);
  return { state };
}
