/**
 * Whether the app is on its way out. Set by `before-quit`: the listener in
 * `./index.ts` calls `markQuitting` first, before any step that can throw, and
 * the one in `./menu.ts` keeps a later mark of its own. Set also,
 * for an update, earlier by `before-quit-for-update` (`./updater.ts`): the
 * install's quit closes every window BEFORE it emits `before-quit`, so without
 * the early mark a window with an unsaved draft would ask Discard/Cancel — and
 * Cancel would strand the restart. Never set by merely asking to install: an
 * install that does not quit must leave the ask working.
 */
let quitting = false;
let forUpdate = false;

export function markQuitting(): void {
  quitting = true;
}

/**
 * The quit an update install starts. The installer (NSIS) or the relaunched
 * AppImage is a child of this process, so the quit deadline must not take the
 * process tree down with it (`./quit-deadline.ts`).
 */
export function markQuittingForUpdate(): void {
  quitting = true;
  forUpdate = true;
}

export function isQuittingForUpdate(): boolean {
  return forUpdate;
}

export function isQuitting(): boolean {
  return quitting;
}
