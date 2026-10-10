import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { PLOT_TOOL } from "../tools.js";

const EMPTY = Object.freeze([]);
let measurementSequence = 0;

/**
 * Measure on a board: two picks make a measurement, read back in the script's millimetres. The
 * point under the pointer before the second pick (the draft) lives in a ref and repaints the canvas;
 * the first pick and the measurements are React state, for the panel.
 *
 * Leaving Measure cancels its unfinished pick; its measurements stay, with their panel. A new
 * revision clears them: they are distances on the board as it was.
 *
 * @param {{ index: object | null, toolMode: string, requestPaint: () => void }} options
 */
export function useBoardMeasure({ index, toolMode, requestPaint }) {
  const [mode, setMode] = useState("all");
  const [measurements, setMeasurements] = useState(EMPTY);
  const [start, setStart] = useState(null);
  const draftRef = useRef(null);

  const cancel = useCallback(() => { setStart(null); draftRef.current = null; requestPaint(); }, [requestPaint]);
  const clear = useCallback(() => { setMeasurements(EMPTY); setStart(null); draftRef.current = null; }, []);
  useEffect(() => { if (index) clear(); }, [index, clear]);
  useEffect(() => { if (toolMode !== PLOT_TOOL.MEASURE) cancel(); }, [toolMode, cancel]);

  /** A pick (`{ page, label, selector }`): the first point, then the measurement. */
  const pick = useCallback((picked) => {
    if (!picked) return;
    if (!start) { setStart(picked); return; }
    // The same point again (a double-click's second press) measures nothing.
    if (picked.page[0] === start.page[0] && picked.page[1] === start.page[1]) return;
    measurementSequence += 1;
    const measurement = { id: `m${measurementSequence}`, a: start, b: picked };
    setMeasurements((current) => [...current, measurement]);
    setStart(null);
  }, [start]);
  /** The point under the pointer; drawn only from a first pick on. Answers whether it is drawn. */
  const draft = useCallback((picked) => { draftRef.current = picked; return Boolean(start); }, [start]);
  const remove = useCallback((id) => setMeasurements((current) => current.filter((item) => item.id !== id)), []);

  const measured = useMemo(() => (index ? measurements.map((measurement) => {
    const [ax, ay] = index.toScript(measurement.a.page);
    const [bx, by] = index.toScript(measurement.b.page);
    return { ...measurement, distance: Math.hypot(bx - ax, by - ay), dx: bx - ax, dy: by - ay };
  }) : EMPTY), [index, measurements]);

  return { mode, setMode, measurements: measured, start, draftRef, pick, draft, cancel, clear, remove };
}
