/**
 * Streamdown's math plugin, loaded with the first formula.
 *
 * `@streamdown/math` imports `rehype-katex` — and through it KaTeX, ~0.6 MB —
 * at its top level, and Streamdown takes the plugin as a plain object, so
 * handing it over statically put the typesetter in the window's first chunk
 * for a transcript that almost never holds a formula. Unlike Mermaid's, this
 * one is a rehype plugin that runs synchronously, so it cannot be stood in for:
 * the plugin list is chosen per render instead. A text with no math in it never
 * asks for the module; the first one that does starts the import, is drawn
 * without typesetting for as long as that takes, and re-renders when it lands.
 * KaTeX's stylesheet comes with it — nothing else in the app loads it.
 */
import type { math as stockMath } from "@streamdown/math";
import { useEffect, useSyncExternalStore } from "react";

type MathPlugin = typeof stockMath;

let loaded: MathPlugin | undefined;
let loading: Promise<void> | undefined;
const listeners = new Set<() => void>();

const load = () =>
  (loading ??= Promise.all([import("@streamdown/math"), import("katex/dist/katex.min.css")]).then(
    ([module]) => {
      loaded = module.math;
      for (const listener of listeners) listener();
    },
    (error: unknown) => {
      // A failed import (a broken bundle) is retried by the next text with math in it.
      loading = undefined;
      console.error("math: could not load the typesetter", error);
    },
  ));

const subscribe = (listener: () => void) => {
  listeners.add(listener);
  return () => void listeners.delete(listener);
};

/**
 * Whether markdown may hold a formula: `$$…$$`, `$…$`, `\(…\)` or `\[…\]`. A
 * superset of what the plugin typesets (it leaves a lone `$` alone), because a
 * false positive only loads the module early.
 */
export function hasMath(source: string): boolean {
  return /\$\$|\\[([]|\$[^\s$][^$]*\$/.test(source);
}

/** The math plugin once it has loaded, for a text that may need it; `undefined` before, and always for one that cannot. */
export function useMathPlugin(source: unknown): MathPlugin | undefined {
  const plugin = useSyncExternalStore(subscribe, () => loaded);
  const needed = typeof source === "string" && hasMath(source);
  useEffect(() => {
    if (needed && !loaded) void load();
  }, [needed]);
  return needed ? plugin : undefined;
}
