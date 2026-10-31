import { useEffect, useRef } from 'react';

/** How often a card asks whether the engine came back with another release. */
export const RELEASE_POLL_MS = 500;

/**
 * A card's update: while `watching` (its own click restarts the engine, or its engine went from under
 * it), the card asks the engine its release (`read`, `GET /__cad/version` through the host), and once
 * one answers with another release than the card's own (`release`), the card loads the engine's app
 * in place of its own (`onNewRelease`: the shell's `reload`, `host/shell.ts`). A read that fails is the
 * engine still away; the same release answering is a blip.
 */
export function useNextRelease({ read, release, watching, onNewRelease }: {
  read: () => Promise<{ release?: string }>;
  release: string | undefined;
  watching: boolean;
  onNewRelease: () => void;
}) {
  const latest = useRef({ read, release, onNewRelease });
  latest.current = { read, release, onNewRelease };
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
        timer = setTimeout(ask, RELEASE_POLL_MS);
      }, () => { if (active) timer = setTimeout(ask, RELEASE_POLL_MS); });
    };
    timer = setTimeout(ask, RELEASE_POLL_MS);
    return () => { active = false; if (timer !== null) clearTimeout(timer); };
  }, [watching]);
}

/** The engine's app loaded in place of this one, by the shell that loaded it; with no shell (this page is the resource itself), the page loaded again. */
export function loadNextRelease() {
  const shell = globalThis.__cadShell;
  if (shell) void shell.reload().catch(() => window.location.reload());
  else window.location.reload();
}
