// The shared component-tessellation cache, reached through THIS surface's
// backend.
//
// The viewer is a consumer of cadgen's shared tessellation cache
// (`~/.cache/cadgen`'s mesh index, served by `cadgen viewer` on
// `/__tess_cache/`): a component load asks the cache before tessellating and
// writes its result back on a miss, so a tessellation done once is done for
// every later open, every snapshot and every export of the same component.
// The provider is one per page (`setTessellationCacheProvider` in cadgen-js,
// which is React-free and takes the origin as a plain argument), and it has
// to point at the backend the surface talks to: an embedded surface's routes
// live on `origin`, not on the page's own.
//
// Before this module the standalone entry (`main.jsx`) registered a
// same-origin provider at bootstrap and an embedded surface registered
// nothing — so the desktop app re-tessellated every component of every model
// on every open, and its viewer's cache stayed empty. Now the surface installs
// the provider for its origin when it mounts (`CadFileView`), and the
// standalone shell is just the `""` case.
//
// One provider per page means the LAST mounted surface's origin serves the
// cache. That is right today — a host mounts one surface at a time — and safe
// regardless: every `cadgen viewer` a host runs reads and writes the same
// store, so a write through either origin lands where the other will find it.
// Nothing here is load-bearing for correctness: an origin that has gone away
// answers every lookup as a miss and swallows every write-back.
import {
  configureTessellationCacheWriteBack,
  createHttpTessellationCacheProvider,
  setTessellationCacheProvider,
} from "cadgen-js/lib/surf/tessellationCache.js";

import { normalizeViewerOrigin } from "./viewerOrigin.js";

// The server's cross-site POST guard: only the write-backs need it, but it is
// harmless on GETs and keeps the provider to one line.
export const VIEWER_POST_GUARD_HEADERS = Object.freeze({ "x-cadgen-viewer": "1" });

// Write-backs wait until the load has gone quiet, then trickle: a cold open of
// a 483-component model issued 483 PUTs against the backend still streaming
// its surfs and took 37 s instead of 27. Two at a time keeps the drain out of
// the next load's way; the backend answers a PUT in ~50 ms when idle.
export const VIEWER_WRITE_BACK_POLICY = Object.freeze({ deferMs: 1500, concurrency: 2 });

export function createViewerTessellationCacheProvider(origin = "") {
  return createHttpTessellationCacheProvider({
    origin: normalizeViewerOrigin(origin),
    headers: { ...VIEWER_POST_GUARD_HEADERS },
  });
}

/** Make `origin`'s cache the page's, with the viewer's write-back policy. Returns the provider installed. */
export function installViewerTessellationCacheProvider(origin = "") {
  const provider = createViewerTessellationCacheProvider(origin);
  setTessellationCacheProvider(provider);
  configureTessellationCacheWriteBack(VIEWER_WRITE_BACK_POLICY);
  return provider;
}
