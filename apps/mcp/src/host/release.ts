declare global {
  // eslint-disable-next-line no-var
  var __cadFollowedUpdate: string | undefined;
}

/** The tab's note, for a page with no shell, which is loaded again (`loadNextRelease`). */
const FOLLOWED_KEY = 'text-to-cad.update.followed';

/**
 * The release the app this one replaced followed an update from (`loadNextRelease`), or null: the app loaded in
 * its place says it is updated, once. Only read: React renders twice in strict mode, so the note is forgotten
 * apart (`forgetFollowedUpdate`).
 */
export function followedUpdate(): string | null {
  if (globalThis.__cadFollowedUpdate) return globalThis.__cadFollowedUpdate;
  try { return window.sessionStorage.getItem(FOLLOWED_KEY) || null; } catch { return null; }
}

/** The note gone, once the app loaded has taken it. */
export function forgetFollowedUpdate() {
  globalThis.__cadFollowedUpdate = undefined;
  try { window.sessionStorage.removeItem(FOLLOWED_KEY); } catch { /* nothing kept, nothing to forget */ }
}

/**
 * The engine's app, of the release an update moved it to, loaded in place of this one (`from`, its release) by the
 * shell that loaded it (`host/shell.ts`'s `reload`); with no shell (this page is the resource itself), the page
 * loaded again. Either way the app loaded is told it followed the update (`followedUpdate`): the shell's app reads
 * the note in the realm they share, a page loaded again in its tab's session storage, which a sandbox may refuse
 * (then the page loaded says nothing). False where neither can be: a shell kept from a release before it could
 * load another app in its place, whose card is then closed and opened again.
 */
export function loadNextRelease(from: string): boolean {
  const shell = globalThis.__cadShell;
  if (shell && typeof shell.reload !== 'function') return false;
  globalThis.__cadFollowedUpdate = from || '?';
  try { window.sessionStorage.setItem(FOLLOWED_KEY, from || '?'); } catch { /* a page loaded again says nothing */ }
  if (shell) void shell.reload!().catch(() => window.location.reload());
  else window.location.reload();
  return true;
}
