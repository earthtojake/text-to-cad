import { useCallback, useMemo, useState } from "react";

const EMPTY = Object.freeze([]);

/** What was isolated as the file's view kept it: a list of the picks' ids, strings only. */
export function readIsolation(raw) {
  return Array.isArray(raw) ? raw.filter((id) => typeof id === "string") : EMPTY;
}

/**
 * The parts and nets a person isolated with a Circuit row's eye (`kit/inspector/CircuitTree.jsx`, a board's
 * and a schematic's): everything else on the canvas steps back, as it does for a net in focus. It is the
 * file's (a renderer slice, `isolated`), named in the file's references (`index.resolve`), so it survives a rebuild: what
 * no longer names anything on the new revision is dropped, and the rest stays. Until the document's
 * index is in, the stored set is kept as it was.
 *
 * @param {{ index: object | null, restored: readonly string[], canonical(id: string): string | undefined }} options  `restored`: the
 *   stored slice; `canonical`: a pick's id as the file writes it, or nothing when the index names nothing by it.
 */
export function useIsolation({ index, restored, canonical: canonicalOf }) {
  const [chosen, setChosen] = useState(null);
  const all = chosen || restored;
  const isolated = useMemo(() => (index ? all.filter((id) => index.resolve(id)) : all), [index, all]);
  const resolved = useMemo(() => (index ? isolated.map((id) => index.resolve(id)).filter(Boolean) : EMPTY), [index, isolated]);
  /** A row's eye: isolate what `id` names, or let everything back in if it already was. */
  const toggle = useCallback((id) => {
    const canonical = index ? canonicalOf(id) : undefined;
    if (!canonical) return;
    setChosen((current) => {
      const kept = (current || restored).filter((item) => index.resolve(item));
      return kept.includes(canonical) ? kept.filter((item) => item !== canonical) : [...kept, canonical];
    });
  }, [index, restored, canonicalOf]);
  return { isolated, resolved, toggle };
}
