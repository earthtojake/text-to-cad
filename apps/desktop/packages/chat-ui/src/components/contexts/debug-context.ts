/**
 * DebugContext — controls the layout-boundary overlay in BlockFrame and Row.
 *
 * When debug is true, each block renders a dashed boundary at the exact height
 * the layout engine reserved. If the real DOM height diverges from the reserved
 * height the outline turns red — that signals a Tailwind class (or other CSS)
 * that added geometry the engine didn't account for.
 *
 * Usage:
 *   1. Set `debug` on ChatRoot (or pass the provider directly in tests/stories).
 *   2. Toggle the "Debug" toolbar item in Storybook to see overlays on all rows.
 */

import { createContext, useContext } from 'solid-js';

export const DebugContext = createContext<() => boolean>(() => false);

/**
 * Returns the reactive debug accessor. Call it inside JSX — `<Show when={useDebug()()}>` —
 * or capture as `const debug = useDebug(); ... <Show when={debug()}>` so Solid's
 * tracking picks up changes when the Storybook toolbar toggles.
 *
 * Do NOT call it immediately (i.e. `useDebug()()`) at component init — that
 * captures a static snapshot that won't react to context changes.
 */
export function useDebug(): () => boolean {
  return useContext(DebugContext);
}
