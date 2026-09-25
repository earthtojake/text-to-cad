import { useCallback, useEffect, useRef, useState } from "react";
import {
  applyMeasureRulerDelete,
  applyMeasureRulerHover,
  applyMeasureRulerPick,
  cancelMeasureRulerDraft,
  measureFilterAccepts,
  measureRulerStateForChange
} from "./measureRulerState.js";

const NO_MEASUREMENTS = Object.freeze([]);

/**
 * The Measure tool's session in a STEP: what its snapping filter is, the measurement being
 * drawn and the ones taken, and which row is highlighted. The viewport feeds it picks and
 * hovers; the panel reads the measurements; the toolbar reads and sets the filter.
 *
 * Measurements outlive the tool (they are cleared on purpose, or with the file's geometry);
 * a draft does not — putting the tool down drops it. The filter goes back to "all" for a new
 * file. The highlighted row follows a new measurement, and otherwise stays where the person
 * put it until that row is gone; only a change to the LIST moves it, so a draft's hover ticks
 * never fight a row click.
 *
 * @param {{ fileKey: string, revision: string, picking: boolean }} options  `picking`: the tool
 *   is in hand and can pick now.
 */
export function useStepMeasure({ fileKey, revision, picking }) {
  const [filter, setFilter] = useState("all");
  useEffect(() => setFilter("all"), [fileKey]);
  const [state, setState] = useState(null);
  const [activeId, setActiveId] = useState("");
  const onPick = useCallback((pick) => {
    if (measureFilterAccepts(filter, pick?.snapKind)) setState((current) => applyMeasureRulerPick(current, pick));
  }, [filter]);
  const onHoverPoint = useCallback((hover) => {
    setState((current) => applyMeasureRulerHover(current, measureFilterAccepts(filter, hover?.snapKind) ? hover : null));
  }, [filter]);
  const onDelete = useCallback((id) => setState((current) => applyMeasureRulerDelete(current, id)), []);
  const cancelDraft = useCallback(() => setState((current) => cancelMeasureRulerDraft(current)), []);
  const clear = useCallback(() => { setState(null); setActiveId(""); }, []);
  const measurements = state?.measurements || NO_MEASUREMENTS;
  useEffect(() => {
    setState((current) => measureRulerStateForChange(current, { entryChanged: true }));
  }, [fileKey, revision]);
  useEffect(() => {
    if (!picking) setState((current) => measureRulerStateForChange(current, { toolActive: false }));
  }, [picking]);
  const countRef = useRef(0);
  useEffect(() => {
    const count = measurements.length;
    const grew = count > countRef.current;
    countRef.current = count;
    const newest = count ? measurements[count - 1].id : "";
    setActiveId((current) => (!grew && current && measurements.some((item) => item.id === current) ? current : newest));
  }, [measurements]);
  return { filter, setFilter, state, measurements, activeId, setActiveId, drafting: Boolean(state?.draft?.anchor),
    onPick, onHoverPoint, onDelete, cancelDraft, clear };
}
