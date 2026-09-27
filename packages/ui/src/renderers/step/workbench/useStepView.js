import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { readFileView } from "../../kit/shell/fileView.js";
import { readStepView, stepViewSignatures, stepViewSlices } from "./stepViewSlices.js";

/**
 * This STEP's own slices of the file's view (`stepViewSlices.js` says what is in them): read
 * once, before the first paint, and written soon after anything in them changes.
 *
 * - `restore(view)` is handed the stored slices as they apply to the entry on screen, once.
 * - `rendererState` is what the shell takes: the signatures the slices are written against, and
 *   `read()`, the slices as the surface stands when the view is written. The inputs are this render's.
 * - `readStored()` reads the stored slices again against the entry as it is NOW, for work that
 *   finishes later (a sidecar that compiles after the first paint).
 * - `scheduleSave` is asked to save after every change to an input.
 *
 * @param {{ state: unknown, entry: object, tree: object, parameterValues: object, largeFileState: object,
 *   scheduleSave: () => void, restore: (view: ReturnType<typeof readStepView>) => void }} options
 */
export function useStepView({ state, entry, tree, parameterValues, largeFileState, scheduleSave, restore }) {
  const [stored] = useState(() => state);
  const signatures = useMemo(() => stepViewSignatures(entry), [entry]);
  const inputsRef = useRef(null);
  inputsRef.current = { tree, parameterValues, largeFileState };
  const rendererState = useMemo(() => ({ signatures, read: () => stepViewSlices(inputsRef.current) }), [signatures]);
  const readStored = useCallback(() => readStepView(readFileView(stored, signatures).renderer), [stored, signatures]);
  useEffect(() => { scheduleSave(); }, [scheduleSave, tree.expandedStepTreeNodeIds, tree.hiddenPartIds, tree.isolatedAssemblyNodeIds,
    parameterValues, largeFileState, signatures]);
  const restored = useRef(false);
  useLayoutEffect(() => {
    if (restored.current) return;
    restored.current = true;
    restore(readStored());
  }, []);
  return { rendererState, readStored };
}
