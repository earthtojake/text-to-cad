import { useEffect, useRef } from 'react';

/** How often a card asks whether the engine came back with another release. */
export const RELEASE_POLL_MS = 500;

/**
 * A card's update: while `watching` (its own click restarts the engine, or its engine went from under
 * it), the card asks the engine who it is (`read`, `GET /api/v1/server` through the host), and once
 * one answers with another release than the card's own (`release`), the card loads the engine's app
 * in place of its own (`onNewRelease`: the shell's `reload`, `host/shell.ts`). An answer of the card's
 * own release goes to `onSameRelease`: a switch that failed and went back says so there (the update's
 * `failed` state, which `useUpdate`'s `settle` ends the restart on), else it is a blip. A read that
 * fails is the engine still away.
 */
export function useNextRelease<Reply extends { release?: string }>({ read, release, watching, onNewRelease,
  onSameRelease }: {
  read: () => Promise<Reply>;
  release: string | undefined;
  watching: boolean;
  onNewRelease: () => void;
  onSameRelease?: (reply: Reply) => void;
}) {
  const latest = useRef({ read, release, onNewRelease, onSameRelease });
  latest.current = { read, release, onNewRelease, onSameRelease };
  useEffect(() => {
    if (!watching || !latest.current.release) return;
    let active = true;
    let timer: ReturnType<typeof setTimeout> | null = null;
    const ask = () => {
      timer = null;
      void latest.current.read().then(reply => {
        if (!active) return;
        if (reply.release && reply.release !== latest.current.release) {
          active = false;
          latest.current.onNewRelease();
          return;
        }
        latest.current.onSameRelease?.(reply);
        if (active) timer = setTimeout(ask, RELEASE_POLL_MS);
      }, () => { if (active) timer = setTimeout(ask, RELEASE_POLL_MS); });
    };
    timer = setTimeout(ask, RELEASE_POLL_MS);
    return () => { active = false; if (timer !== null) clearTimeout(timer); };
  }, [watching]);
}

declare global {
  // eslint-disable-next-line no-var
  var __cadFollowedUpdate: boolean | undefined;
}

/** The tab's note, for a page with no shell, which is loaded again (`loadNextRelease`). */
const FOLLOWED_KEY = 'text-to-cad.update.followed';

/**
 * Whether the app this one replaced followed an update to the engine's release (`loadNextRelease`): the
 * app loaded in its place says it once. Only read: React renders twice in strict mode, so the note is
 * forgotten apart (`forgetFollowedUpdate`).
 */
export function followedUpdate(): boolean {
  if (globalThis.__cadFollowedUpdate) return true;
  try { return window.sessionStorage.getItem(FOLLOWED_KEY) === '1'; } catch { return false; }
}

/** The note gone, once the app loaded has taken it. */
export function forgetFollowedUpdate() {
  globalThis.__cadFollowedUpdate = undefined;
  try { window.sessionStorage.removeItem(FOLLOWED_KEY); } catch { /* nothing kept, nothing to forget */ }
}

/**
 * The engine's app loaded in place of this one, by the shell that loaded it; with no shell (this page is
 * the resource itself), the page loaded again. Either way the app loaded is told it followed the update
 * (`followedUpdate`): the shell's app reads the note in the realm they share, a page loaded again in its
 * tab's session storage, which a sandbox may refuse (then the page loaded says nothing).
 */
export function loadNextRelease() {
  const shell = globalThis.__cadShell;
  globalThis.__cadFollowedUpdate = true;
  try { window.sessionStorage.setItem(FOLLOWED_KEY, '1'); } catch { /* a page loaded again says nothing */ }
  if (shell) void shell.reload().catch(() => window.location.reload());
  else window.location.reload();
}
