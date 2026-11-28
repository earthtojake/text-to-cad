/**
 * The project's notices the person dismissed in this CAD app (`useUpdate`'s `notices`, `@cad/ui/update`): their ids,
 * kept in the frame's local storage, so a notice dismissed in one view stays dismissed in the next. A host whose frame
 * keeps nothing (storage blocked, or none) reads none and keeps none: the notice is shown again in the next view, and
 * nothing fails.
 */
const KEY = "text-to-cad.notices.dismissed";

type Kept = Pick<Storage, "getItem" | "setItem">;

function storageOf(storage?: Kept): Kept {
  return storage ?? window.localStorage;
}

/** The ids dismissed in this app's frame. */
export function dismissedNotices(storage?: Kept): string[] {
  try {
    const kept: unknown = JSON.parse(storageOf(storage).getItem(KEY) || "[]");
    return Array.isArray(kept) ? kept.filter((id): id is string => typeof id === "string") : [];
  } catch {
    return [];
  }
}

/** A notice dismissed, kept with the others. */
export function dismissNotice(id: string, storage?: Kept): void {
  try {
    const kept = dismissedNotices(storage);
    if (!kept.includes(id)) storageOf(storage).setItem(KEY, JSON.stringify([...kept, id]));
  } catch {
    // nothing kept: shown again in the next view
  }
}

/** This app's dismissals, as `useUpdate` takes them. */
export const frameNoticeDismissals = { dismissed: () => dismissedNotices(), dismiss: (id: string) => dismissNotice(id) };
