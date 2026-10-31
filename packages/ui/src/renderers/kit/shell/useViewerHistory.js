import { useMemo, useRef, useState } from "react";
import { useControlUsage } from "../../../usage/controls.js";

const LIMIT = 200;

/**
 * One file view's undo history, across its tools: each step a tool takes records how to take it
 * back and do it again (`record`), and Undo and Redo walk the one list, whichever tool took the
 * step. Only what a person makes is a step — ink, a measurement — never the camera or a
 * selection. A tool whose work is gone (the annotation discarded with its model) takes its steps
 * out (`forget`).
 *
 * @typedef {{ source: string, undo: () => void, redo: () => void }} ViewerHistoryStep
 * @typedef {{ canUndo: boolean, canRedo: boolean, record(step: ViewerHistoryStep): void,
 *   undo(): boolean, redo(): boolean, forget(source: string): void }} ViewerHistory
 * @returns {ViewerHistory}
 */
export function useViewerHistory() {
  const controls = useControlUsage();
  const stacks = useRef({ past: /** @type {ViewerHistoryStep[]} */ ([]), future: /** @type {ViewerHistoryStep[]} */ ([]) });
  const [sizes, setSizes] = useState({ past: 0, future: 0 });
  const actions = useMemo(() => {
    const publish = () => {
      const { past, future } = stacks.current;
      setSizes(current => (current.past === past.length && current.future === future.length ? current
        : { past: past.length, future: future.length }));
    };
    return {
      record(step) {
        stacks.current = { past: [...stacks.current.past, step].slice(-LIMIT), future: [] };
        publish();
      },
      undo() {
        const { past, future } = stacks.current;
        const step = past[past.length - 1];
        if (!step) return false;
        stacks.current = { past: past.slice(0, -1), future: [step, ...future] };
        step.undo();
        controls.used("undo");
        publish();
        return true;
      },
      redo() {
        const { past, future } = stacks.current;
        const step = future[0];
        if (!step) return false;
        stacks.current = { past: [...past, step], future: future.slice(1) };
        step.redo();
        controls.used("redo");
        publish();
        return true;
      },
      forget(source) {
        const { past, future } = stacks.current;
        stacks.current = { past: past.filter(step => step.source !== source), future: future.filter(step => step.source !== source) };
        publish();
      },
    };
  }, [controls]);
  return useMemo(() => ({ canUndo: sizes.past > 0, canRedo: sizes.future > 0, ...actions }), [sizes, actions]);
}
