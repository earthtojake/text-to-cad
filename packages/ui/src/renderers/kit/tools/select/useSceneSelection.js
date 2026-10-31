import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const EMPTY = Object.freeze([]);

// Toggle for a modified click, replace for a plain one, and a second plain click on the one
// selected part clears it: the rule every selecting view in the viewer follows.
function nextSelection(current, id, multiSelect) {
  if (!id) return EMPTY;
  if (multiSelect) return current.includes(id) ? current.filter(candidate => candidate !== id) : [...current, id];
  return current.length === 1 && current[0] === id ? EMPTY : [id];
}

/**
 * What is selected and hovered in a scene whose parts a pick names (`scene.pick(ray)`'s `id`, the
 * file's own id for the part). The scene draws both (`scene.setHighlight`).
 * Selection is React state, because Quick Edit's chips draw it; hover is not, because nothing but
 * the scene shows it and it changes as the pointer moves. A new revision of the file keeps what it
 * still has.
 *
 * `requestRender` asks the viewport for the frame that shows a changed highlight: one that keeps
 * the shadow maps, since a highlight moves and reshapes nothing.
 *
 * @param {{ scene: { setHighlight?: (ink: { hovered: string[], selected: string[] }) => void,
 *   hasPart?: (id: string) => boolean } | null, requestRender: () => void }} options
 */
export function useSceneSelection({ scene, requestRender }) {
  const [chosen, setChosen] = useState(EMPTY);
  const hovered = useRef("");
  const selected = useMemo(() => (scene?.hasPart ? chosen.filter(id => scene.hasPart(id)) : EMPTY), [scene, chosen]);
  const live = useRef(null);
  live.current = { scene, requestRender, selected };
  const paint = useCallback(() => {
    const now = live.current;
    if (!now.scene?.setHighlight) return;
    now.scene.setHighlight({ hovered: hovered.current ? [hovered.current] : [], selected: now.selected });
    now.requestRender();
  }, []);
  useEffect(paint, [paint, scene, selected]);
  const hover = useCallback((id) => {
    const next = String(id || "");
    if (hovered.current === next) return;
    hovered.current = next;
    paint();
  }, [paint]);
  const select = useCallback((id, { multiSelect = false } = {}) => setChosen(current => nextSelection(current, String(id || ""), multiSelect)), []);
  const clear = useCallback(() => setChosen(current => (current.length ? EMPTY : current)), []);
  // A viewport pick: the part under the pointer, and nothing clears.
  const pick = useCallback((hit, { multiSelect = false } = {}) => (hit ? select(hit.id, { multiSelect }) : clear()), [select, clear]);
  const hoverHit = useCallback(hit => hover(hit?.id || ""), [hover]);
  return { selected, active: selected.length > 0, select, clear, pick, hover, hoverHit };
}
