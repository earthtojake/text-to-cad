import { createContext, useCallback, useContext, useRef } from "react";

/**
 * Moving through the folder of its project a document is in, one file at a time: `[` the previous and `]` the next,
 * in the order that folder's page lists them, stopping at its ends.
 *
 * `FileViewer` works the two out of its `project` (`projectNeighbours`) and hands them to the view under it
 * (`ProjectKeysContext`, a ref that never changes, so a project read again re-renders no view) and to its ⋯ (Previous
 * in project, Next in project). The view's own keys reach them (`useProjectKey`), so they are single keys under the
 * rule every single key keeps (`kit/shell/useViewerShortcuts.js`):
 * no ⌘, Ctrl or Alt, no repeat, never in a text field, only while this viewer has the keyboard; and the view leaves
 * them in Preview.
 *
 * @typedef {{ previous: (() => void) | null, next: (() => void) | null }} ProjectNeighbours
 */

/** @type {import("react").Context<{ current: ProjectNeighbours | null } | null>} */
export const ProjectKeysContext = createContext(null);

const slashed = path => String(path || "").replace(/\\/g, "/").replace(/\/+$/, "");

/**
 * The documents before and after `current` (the document on screen, by its file's path or its id: either names it)
 * among a folder's `documents`, skipping one that is gone (`missing`), each null at an end; null where `current` is not
 * one of them or the folder has no other.
 *
 * @template {{ path: string, id?: string, missing?: boolean }} Row
 * @param {readonly Row[] | null | undefined} documents
 * @param {string | null | undefined | readonly (string | null | undefined)[]} current
 * @returns {{ previous: Row | null, next: Row | null } | null}
 */
export function projectNeighbours(documents, current) {
  const names = new Set([current].flat().filter(Boolean).map(slashed));
  if (!documents || documents.length < 2 || !names.size) return null;
  const at = documents.findIndex(row => names.has(slashed(row.path)) || Boolean(row.id && names.has(row.id)));
  if (at < 0) return null;
  const find = by => { for (let index = at + by; index >= 0 && index < documents.length; index += by) if (!documents[index].missing) return documents[index]; return null; };
  return { previous: find(-1), next: find(1) };
}

/**
 * The view's handler for `[` and `]`: true when it moved to another document (the key is then the view's), false at
 * an end, for any other key, or where the document is in no project. Read through a ref, so a view binds it once.
 *
 * @returns {(event: KeyboardEvent) => boolean}
 */
export function useProjectKey() {
  const neighbours = useContext(ProjectKeysContext);
  const latest = useRef(neighbours);
  latest.current = neighbours;
  return useCallback(event => {
    if (event.shiftKey) return false;
    const now = latest.current?.current;
    const go = event.key === "[" ? now?.previous : event.key === "]" ? now?.next : null;
    if (!go) return false;
    go();
    return true;
  }, []);
}
