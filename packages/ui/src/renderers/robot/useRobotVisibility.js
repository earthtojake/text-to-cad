import { useCallback, useLayoutEffect, useMemo, useState } from "react";
import { readFileView } from "../kit/shell/fileView.js";
import { changeRobotVisibility } from "./visibility.js";

const EMPTY = Object.freeze([]);

/**
 * Which visuals are hidden: React state, since the Links rows draw it, scoped to this file. The
 * `visibility` slice of the file's view restores it against the payload's revision, and a live
 * reload keeps only the ids the loaded part list still has. The scene is told on every change.
 */
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
