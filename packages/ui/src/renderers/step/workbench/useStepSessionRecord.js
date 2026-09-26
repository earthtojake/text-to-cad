import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { readShellState } from "../../kit/shell/shellState.js";
import { readStepRecord, stepRecordInputs, stepRecordSignatures, writeStepRecord } from "./stepSessionRecord.js";

/**
 * This STEP's own slice of the shell's per-file record (`stepSessionRecord.js` says what is in
 * it): read once, before the first paint, and written soon after anything in it changes.
 *
 * - `restore(record)` is handed the stored slice as it applies to the entry on screen, once.
 * - `write()` is the shell's `rendererState`: the record as the surface stands when it is
 *   written. The inputs are this render's.
 * - `readStored()` reads the stored slice again against the entry as it is NOW, for work that
 *   finishes later (a sidecar or a routine that compiles after the first paint).
 * - `scheduleSave` is asked to save after every change to an input; it decides whether now is
 *   a time to save (a PLAYING clip never is: its time moves every frame).
 *
 * @param {{ state: unknown, entry: object, tree: object, parameterValues: object, animationState: object,
 *   clockTime: () => number, largeFileState: object, annotations: object[], scheduleSave: () => void,
 *   restore: (record: object) => void }} options
 */
export function useStepSessionRecord({ state, entry, tree, parameterValues, animationState, clockTime, largeFileState, annotations, scheduleSave, restore }) {
  const [stored] = useState(() => readShellState(state).renderer);
  const signatures = useMemo(() => stepRecordSignatures(entry), [entry]);
  const signaturesRef = useRef(signatures);
  signaturesRef.current = signatures;
  const inputsRef = useRef(null);
  inputsRef.current = stepRecordInputs({ tree, parameterValues, animationState, clockTime, largeFileState, annotations, signatures });
  const write = useCallback(() => writeStepRecord(inputsRef.current), []);
  const readStored = useCallback(() => readStepRecord(stored, signaturesRef.current), [stored]);
  useEffect(() => { scheduleSave(); }, [scheduleSave, tree.selectedReferenceIds, tree.selectedPartIds,
    tree.expandedStepTreeNodeIds, tree.hiddenPartIds, parameterValues, animationState, largeFileState, annotations, signatures]);
  const restored = useRef(false);
  useLayoutEffect(() => {
    if (restored.current) return;
    restored.current = true;
    restore(readStepRecord(stored, signatures));
  }, []);
  return { write, readStored };
}
