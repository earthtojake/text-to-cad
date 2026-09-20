import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const EMPTY = Object.freeze([]);
const NOTHING = Object.freeze({ linkName: "", componentIds: EMPTY });

// Toggle for a modified click, replace for a plain one, and a second plain click on the
// one selected object clears it: the rule every selecting tree in the viewer follows.
function nextComponentIds(current, id, multiSelect) {
  if (!id) return EMPTY;
  if (multiSelect) return current.includes(id) ? current.filter(candidate => candidate !== id) : [...current, id];
  return current.length === 1 && current[0] === id ? EMPTY : [id];
}

/**
 * What is selected and hovered in a robot: ONE link, or any number of named mesh objects.
 * The scene graph draws both (`scene.setHighlight`), so there is no table of part ids: a
 * link is its group's meshes. Selection is React state, because the Links tab draws it;
 * hover is not, because nothing but the scene shows it and it changes as the pointer moves.
 *
 * A link is named by the description, so its selection survives a rebuilt scene; an
 * object's id belongs to one built scene and does not.
 *
 * @param {{ scene: object | null, hidden: boolean, requestRender: () => void }} options  `hidden`: highlights
 *   are not drawn (fullscreen), though the selection is kept.
 */
export function useLinkSelection({ scene, hidden, requestRender }) {
  const [selection, setSelection] = useState(NOTHING);
  const hover = useRef({ linkName: "", componentId: "" });
  const live = useRef(null);
  const selectedComponentIds = useMemo(
    () => (scene ? selection.componentIds.filter(id => scene.hasComponent(id)) : EMPTY),
    [scene, selection.componentIds]
  );
  const selectedLinkName = selection.linkName;
  live.current = { scene, hidden, requestRender, selectedLinkName, selectedComponentIds };

  const paint = useCallback(() => {
    const now = live.current;
    if (!now.scene) return;
    now.scene.setHighlight(now.hidden ? {} : {
      hoveredLink: hover.current.linkName, hoveredComponent: hover.current.componentId,
      selectedLink: now.selectedLinkName, selectedComponents: now.selectedComponentIds
    });
    now.requestRender();
  }, []);
  useEffect(paint, [paint, scene, hidden, selectedLinkName, selectedComponentIds]);

  const setHover = useCallback((linkName, componentId) => {
    if (hover.current.linkName === linkName && hover.current.componentId === componentId) return;
    hover.current = { linkName, componentId };
    paint();
  }, [paint]);
  const selectLink = useCallback(linkName => setSelection({ linkName: String(linkName || ""), componentIds: EMPTY }), []);
  const select = useCallback((id, { multiSelect = false } = {}) => {
    setSelection(current => ({ linkName: "", componentIds: nextComponentIds(current.linkName ? EMPTY : current.componentIds, String(id || ""), multiSelect) }));
  }, []);
  const clear = useCallback(() => setSelection(current => (current.linkName || current.componentIds.length ? NOTHING : current)), []);
  // A viewport pick: a named object is itself, any other surface is its link, nothing clears.
  const pick = useCallback((hit, { multiSelect = false } = {}) => {
    if (!hit) clear();
    else if (hit.componentId) select(hit.componentId, { multiSelect });
    else selectLink(hit.linkName);
  }, [clear, select, selectLink]);
  const hoverHit = useCallback(hit => setHover(hit && !hit.componentId ? hit.linkName : "", hit?.componentId || ""), [setHover]);

  return {
    selectedLinkName, selectedComponentIds, active: Boolean(selectedLinkName || selectedComponentIds.length),
    select, selectLink, clear, pick,
    hover: useCallback(id => setHover("", String(id || "")), [setHover]),
    hoverLink: useCallback(linkName => setHover(String(linkName || ""), ""), [setHover]),
    hoverHit
  };
}
