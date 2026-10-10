import { useCallback, useMemo, useState } from "react";

const EMPTY = Object.freeze([]);

/** The isolated slice as the file's view keeps it: `{ selectors }`, strings only. */
export function readBoardIsolation(raw) {
  return Array.isArray(raw?.selectors) ? raw.selectors.filter((selector) => typeof selector === "string") : EMPTY;
}

/**
 * The parts and nets a person isolated with a tree row's eye (`kit/inspector/TreeRowEye.jsx`):
 * everything else on the canvas steps back, as it does for a net or a check in focus. It is the
 * file's (a renderer slice, `isolated`), named in board references, so it survives a rebuild: what
 * no longer names anything on the new revision is dropped, and the rest stays. Until the document's
 * index is in, the stored set is kept as it was.
 *
 * @param {{ index: object | null, restored: readonly string[] }} options  `restored`: the stored slice.
 */
export function useBoardIsolation({ index, restored }) {
  const [chosen, setChosen] = useState(null);
  const all = chosen || restored;
  const isolated = useMemo(() => (index ? all.filter((selector) => index.resolve(selector)) : all), [index, all]);
  const resolved = useMemo(() => (index ? isolated.map((selector) => index.resolve(selector)).filter(Boolean) : EMPTY), [index, isolated]);
  /** A row's eye: isolate what `selector` names, or let everything back in if it already was. */
  const toggle = useCallback((selector) => {
    const canonical = index?.resolve(selector)?.selector;
    if (!canonical) return;
    setChosen((current) => {
      const kept = (current || restored).filter((item) => index.resolve(item));
      return kept.includes(canonical) ? kept.filter((item) => item !== canonical) : [...kept, canonical];
    });
  }, [index, restored]);
  return { isolated, resolved, toggle };
}
