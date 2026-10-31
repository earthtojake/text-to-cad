import { useCallback, useEffect, useRef, useState } from "react";
import { useControlUsage } from "../../../../usage/controls.js";
import {
  applyMeasureRulerDelete,
  applyMeasureRulerHover,
  applyMeasureRulerPick,
  cancelMeasureRulerDraft,
  measureRulerStateForChange
} from "./measureRulerState.js";

const NO_MEASUREMENTS = Object.freeze([]);

/**
 * The Measure tool's session, in any 3D file: the measurement being drawn and the ones taken
 * (between two points, each where the pick snapped: exact vertices, edges and faces where the
 * renderer has them, else a mesh's triangles), and which is highlighted. The viewport feeds it picks and hovers; Quick
 * Edit's chips read the measurements (`measurementChips.jsx`).
 *
 * Measurements outlive the tool (they are cleared on purpose, or with the file's geometry);
 * a draft does not — putting the tool down drops it. The highlighted row follows a new measurement, and otherwise stays where the person
 * put it until that row is gone; only a change to the LIST moves it, so a draft's hover ticks
 * never fight a row click. Under Select, measurements are hovered and picked as anything is
 * (`hovered`/`hover`, `selected`/`select`), haloed in the view, and Delete deletes them
 * (`removeSelected`).
 *
 * Each measurement taken, deleted or cleared is a step of the view's one undo history, with the
 * ink's (`kit/shell/useViewerHistory.js`): `history` is the ref the renderer points at it once its
 * shell is made, so ⌘Z and ⇧⌘Z walk measurements and ink alike. A new file or revision takes the
 * steps out with the measurements.
 *
 * @param {{ fileKey: string, revision: string, picking: boolean }} options  `picking`: the tool
 *   is in hand and can pick now.
 */
export function useMeasureSession({ fileKey, revision, picking }) {
  const [state, setState] = useState(null);
  const [activeId, setActiveId] = useState("");
  // The state as last set, so a change and the step it makes are one synchronous act.
  const stateRef = useRef(null);
  const history = useRef(null);
  const set = useCallback((next) => {
    const before = stateRef.current;
    const after = typeof next === "function" ? next(before) : next;
    stateRef.current = after;
    setState(after);
    return [before?.measurements || NO_MEASUREMENTS, after?.measurements || NO_MEASUREMENTS];
  }, []);
  // A change of the list is a step: undone, the list goes back as it was (the draft, if any, kept as it is now).
  const step = useCallback(([before, after]) => {
    if (before === after || !history.current) return;
    const restore = list => () => set(current => (list.length || current?.draft ? { draft: current?.draft || null, hover: current?.hover || null, measurements: list } : null));
    history.current.record({ source: "measure", undo: restore(before), redo: restore(after) });
  }, [set]);
  // A measurement taken, deleted or cleared by a person, counted (`usage/controls.js`).
  const controls = useControlUsage();
  const onPick = useCallback((pick) => {
    const change = set((current) => applyMeasureRulerPick(current, pick));
    if (change[1].length > change[0].length) controls.used("measure_taken");
    step(change);
  }, [set, step, controls]);
  const onHoverPoint = useCallback((hover) => {
    set((current) => applyMeasureRulerHover(current, hover));
  }, [set]);
  const onDelete = useCallback((id) => { controls.used("measure_delete"); step(set((current) => applyMeasureRulerDelete(current, id))); }, [set, step, controls]);
  const cancelDraft = useCallback(() => set((current) => cancelMeasureRulerDraft(current)), [set]);
  const clear = useCallback(() => { step(set(null)); setActiveId(""); }, [set, step]);
  const measurements = state?.measurements || NO_MEASUREMENTS;
  useEffect(() => {
    set((current) => measureRulerStateForChange(current, { entryChanged: true }));
    history.current?.forget("measure");
  }, [fileKey, revision, set]);
  useEffect(() => {
    if (!picking) set((current) => measureRulerStateForChange(current, { toolActive: false }));
  }, [picking, set]);
  const countRef = useRef(0);
  useEffect(() => {
    const count = measurements.length;
    const grew = count > countRef.current;
    countRef.current = count;
    const newest = count ? measurements[count - 1].id : "";
    setActiveId((current) => (!grew && current && measurements.some((item) => item.id === current) ? current : newest));
  }, [measurements]);
  // What Select has picked: the measurements Delete deletes. A measurement gone takes its pick with it.
  const [selected, setSelected] = useState(NO_MEASUREMENTS);
  useEffect(() => {
    setSelected((current) => (current.every((id) => measurements.some((item) => item.id === id)) ? current
      : current.filter((id) => measurements.some((item) => item.id === id))));
  }, [measurements]);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const removeSelected = useCallback(() => {
    const ids = selectedRef.current;
    if (!ids.length) return false;
    controls.used("measure_delete");
    step(set((current) => ids.reduce((next, id) => applyMeasureRulerDelete(next, id), current)));
    setSelected(NO_MEASUREMENTS);
    return true;
  }, [set, step, controls]);
  // What the pointer rests on under Select: lit as a part is, until it moves off or the measurement goes.
  const [hovered, setHovered] = useState("");
  useEffect(() => {
    setHovered((current) => (current && !measurements.some((item) => item.id === current) ? "" : current));
  }, [measurements]);
  return { state, measurements, history, activeId, setActiveId, drafting: Boolean(state?.draft?.anchor),
    onPick, onHoverPoint, onDelete, cancelDraft, clear, selected, select: setSelected, removeSelected, hovered, hover: setHovered };
}
