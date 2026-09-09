/**
 * CachesContext — Solid context that provides the per-instance ChatCaches bundle
 * to all descendant Render components in the chat tree.
 *
 * ChatRoot (or any test harness) provides the bundle via:
 *   <CachesContext.Provider value={caches}>…</CachesContext.Provider>
 *
 * Render leaf components that need caches (Code.tsx, Diff.tsx, etc.) call
 * `useCaches()` to read the bundle rather than accessing module-level state.
 *
 * The context default is the module-level fallback bundle so that direct-mount
 * tests and stories that don't wrap in a Provider still work.  The fallback is
 * shared across those call sites, which is acceptable for isolated test runs.
 */

import { type ChatCaches, getFallbackCaches } from '@core/caches';
import { createContext, useContext } from 'solid-js';

let _warnedFallback = false;

export const CachesContext = createContext<ChatCaches>(
  // Proxy to the lazily-created fallback so the heavy createChatCaches() call
  // is deferred until the first actual usage rather than at module-load time.
  new Proxy({} as ChatCaches, {
    get(_target, prop: keyof ChatCaches) {
      if (import.meta.env.DEV && !_warnedFallback) {
        _warnedFallback = true;
        console.warn(
          '[chat-ui] useCaches() called without a CachesContext.Provider. ' +
            'Wrap your component tree in <CachesContext.Provider value={caches}> ' +
            'to use an isolated per-instance cache.'
        );
      }
      return getFallbackCaches()[prop];
    },
  })
);

/** Returns the current ChatCaches bundle from the nearest CachesContext. */
export const useCaches = (): ChatCaches => useContext(CachesContext);
