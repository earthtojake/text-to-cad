import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const EMPTY = Object.freeze([]);
const NOTHING = Object.freeze({ linkNames: EMPTY, componentIds: EMPTY });

// Toggle for a modified click, replace for a plain one, and a second plain click on the
// one selected object clears it: the rule every selecting tree in the viewer follows.
function nextComponentIds(current, id, multiSelect) {
  if (!id) return EMPTY;
  if (multiSelect) return current.includes(id) ? current.filter(candidate => candidate !== id) : [...current, id];
  return current.length === 1 && current[0] === id ? EMPTY : [id];
}

// Links toggle the same way under a modified click; a plain click on a link selects that link
// and only it (a second one keeps it: a link is what the Reference pane is reading).
function nextLinkNames(current, name, multiSelect) {
  if (!name) return EMPTY;
  if (multiSelect) return current.includes(name) ? current.filter(candidate => candidate !== name) : [...current, name];
  return [name];
}

/**
 * What is selected and hovered in a robot: links, or named mesh objects — any number of
 * either (a modified click adds), never both at once.
 * The scene graph draws both (`scene.setHighlight`), so there is no table of part ids: a
 * link is its group's meshes. Selection is React state, because the Links section draws it;
 * hover is not, because nothing but the scene shows it and it changes as the pointer moves.
 *
 * A link is named by the description, so its selection survives a rebuilt scene; an
 * object's id belongs to one built scene and does not.
 *
 * @param {{ scene: object | null, requestRender: () => void }} options
 */
export function useLinkSelection({ scene, requestRender }) {
  const [selection, setSelection] = useState(NOTHING);
  const hover = useRef({ linkName: "", componentId: "" });
  const live = useRef(null);
  const selectedComponentIds = useMemo(
    () => (scene ? selection.componentIds.filter(id => scene.hasComponent(id)) : EMPTY),
    [scene, selection.componentIds]
  );
  const selectedLinkNames = selection.linkNames;
  live.current = { scene, requestRender, selectedLinkNames, selectedComponentIds };

  const paint = useCallback(() => {
    const now = live.current;
    if (!now.scene) return;
    now.scene.setHighlight({
      hoveredLink: hover.current.linkName, hoveredComponent: hover.current.componentId,
      selectedLinks: now.selectedLinkNames, selectedComponents: now.selectedComponentIds
    });
    now.requestRender();
  }, []);
  useEffect(paint, [paint, scene, selectedLinkNames, selectedComponentIds]);

  const setHover = useCallback((linkName, componentId) => {
    if (hover.current.linkName === linkName && hover.current.componentId === componentId) return;
    hover.current = { linkName, componentId };
    paint();
  }, [paint]);
  const selectLink = useCallback((linkName, { multiSelect = false } = {}) => {
    setSelection(current => ({ linkNames: nextLinkNames(current.componentIds.length ? EMPTY : current.linkNames, String(linkName || ""), multiSelect), componentIds: EMPTY }));
  }, []);
  const select = useCallback((id, { multiSelect = false } = {}) => {
    setSelection(current => ({ linkNames: EMPTY, componentIds: nextComponentIds(current.linkNames.length ? EMPTY : current.componentIds, String(id || ""), multiSelect) }));
  }, []);
  const clear = useCallback(() => setSelection(current => (current.linkNames.length || current.componentIds.length ? NOTHING : current)), []);
  // A viewport pick: a named object is itself, any other surface is its link, nothing clears.
  const pick = useCallback((hit, { multiSelect = false } = {}) => {
    if (!hit) clear();
    else if (hit.componentId) select(hit.componentId, { multiSelect });
    else selectLink(hit.linkName, { multiSelect });
  }, [clear, select, selectLink]);
  const hoverHit = useCallback(hit => setHover(hit && !hit.componentId ? hit.linkName : "", hit?.componentId || ""), [setHover]);

  return {
    selectedLinkNames, selectedComponentIds, active: Boolean(selectedLinkNames.length || selectedComponentIds.length),
    select, selectLink, clear, pick,
    hover: useCallback(id => setHover("", String(id || "")), [setHover]),
    hoverLink: useCallback(linkName => setHover(String(linkName || ""), ""), [setHover]),
    hoverHit
  };
}
