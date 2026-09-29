import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const NONE = Object.freeze([]);

/**
 * Which leaves of an implicit part's GLB are selected, and which one the pointer is
 * over. The selection is React state (a panel draws it); hover is a ref (only the
 * scene shows it). Toggle rules follow the robot's: a modified click toggles, a plain
 * click replaces, a second plain click on the only selected leaf clears it.
 *
 * @param {{ scene: object | null, requestRender: () => void }} options
 */
export function useLeafSelection({ scene, requestRender }) {
  const [selectedIds, setSelectedIds] = useState(NONE);
  const hover = useRef("");
  const known = useMemo(() => new Set((scene?.leaves || []).map(leaf => leaf.id)), [scene]);
  const selected = useMemo(() => selectedIds.filter(id => known.has(id)), [selectedIds, known]);

  const paint = useCallback(() => {
    if (typeof scene?.setHighlight !== "function") return;
    scene.setHighlight({ hovered: hover.current, selected });
    requestRender();
  }, [scene, selected, requestRender]);
  useEffect(paint, [paint]);

  const select = useCallback((id, { multiSelect = false } = {}) => {
    setSelectedIds(current => {
      if (!id) return NONE;
      if (multiSelect) return current.includes(id) ? current.filter(other => other !== id) : [...current, id];
      return current.length === 1 && current[0] === id ? NONE : [id];
    });
  }, []);
  const clear = useCallback(() => setSelectedIds(NONE), []);
  const setHover = useCallback((id) => {
    const next = id || "";
    if (hover.current === next) return;
    hover.current = next;
    paint();
  }, [paint]);
  const pick = useCallback((hit, { multiSelect = false } = {}) => {
    if (!hit) clear();
    else select(hit.id, { multiSelect });
  }, [clear, select]);
  const hoverHit = useCallback(hit => setHover(hit?.id || ""), [setHover]);

  return { selected, active: selected.length > 0, select, clear, pick, hover: setHover, hoverHit };
}
