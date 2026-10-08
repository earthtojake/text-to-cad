import { useCallback, useLayoutEffect, useMemo, useState } from "react";
import { readFileView } from "../kit/shell/fileView.js";
import { changeRobotVisibility } from "./visibility.js";

const EMPTY = Object.freeze([]);

/** Visibility is local to this file; reloads retain only part identities still present. */
export function useRobotVisibility({ robot, scene, requestRender, stored }) {
  const [visibility, setVisibility] = useState(null);
  const restored = useMemo(() => {
    if (!robot) return EMPTY;
    const ids = readFileView(stored, { visibility: robot.revision }).renderer.visibility?.hiddenPartIds;
    return Array.isArray(ids) ? ids.filter(id => typeof id === "string") : EMPTY;
  }, [robot, stored]);
  const hidden = visibility?.hiddenPartIds || restored;
  const validIds = useMemo(() => new Set((robot?.parts || EMPTY).map(part => part.id)), [robot]);
  const hiddenPartIds = useMemo(() => hidden.filter(id => validIds.has(id)), [hidden, validIds]);
  const changeVisibility = useCallback((partIds, visible) => {
    setVisibility(current => ({ hiddenPartIds: changeRobotVisibility(current?.hiddenPartIds || restored, partIds, visible, validIds) }));
  }, [validIds, restored]);
  useLayoutEffect(() => {
    if (robot) setVisibility(current => ({ hiddenPartIds: (current?.hiddenPartIds || restored).filter(id => validIds.has(id)) }));
  }, [robot, restored, validIds]);
  useLayoutEffect(() => {
    if (!scene) return;
    scene.setHiddenPartIds(hiddenPartIds);
    requestRender();
  }, [scene, hiddenPartIds, requestRender]);
  return { hiddenPartIds, changeVisibility };
}
