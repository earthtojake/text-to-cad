import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

/**
 * What a drawing toolbar needs of a mounted editor; `DrawingController` satisfies it.
 * @typedef {object} DrawingToolbarTarget
 * @property {(tool: import('./toolbar.jsx').DrawingTool) => void} setTool
 * @property {(color: string) => void} setColor
 * @property {() => void} undo
 * @property {() => void} redo
 * @property {() => void} clear
 */
/**
 * @typedef {object} DrawingSession
 * @property {boolean} ready
 * @property {string} tool
 * @property {string} color
 * @property {boolean} hasContent
 * @property {(tool: import('./toolbar.jsx').DrawingTool) => void} selectTool
 * @property {(color: string) => void} selectColor
 * @property {() => void} undo
 * @property {() => void} redo
 * @property {() => void} clear
 * @property {(target: DrawingToolbarTarget | null) => void} onReady
 * @property {(tool: string) => void} onToolChange
 * @property {(color: string) => void} onColorChange
 * @property {(hasContent: boolean) => void} onContentChange
 */

/**
 * One drawing session: a toolbar's view of the mounted editor and its only way
 * to drive it. The sketch itself lives in the editor; an inactive session (the
 * CAD Draw tool deselected) forgets everything, as the unmounted editor did.
 *
 * @param {boolean} [active]
 * @param {{ tool?: string, color?: string }} [initial]
 * @returns {DrawingSession}
 */
export function useDrawingSession(active = true, initial = {}) {
  const idle = useMemo(() => ({ ready: false, tool: initial.tool ?? 'selection', color: initial.color ?? '#1e1e1e', hasContent: false }), [initial.tool, initial.color]);
  const target = useRef(/** @type {DrawingToolbarTarget | null} */ (null));
  const [state, setState] = useState(idle);
  useEffect(() => { if (!active) { target.current = null; setState(idle); } }, [active, idle]);
  const onReady = useCallback((/** @type {DrawingToolbarTarget | null} */ next) => {
    target.current = next;
    setState(current => next ? { ...current, ready: true } : idle);
  }, [idle]);
  const report = useCallback((/** @type {'tool' | 'color' | 'hasContent'} */ key, /** @type {string | boolean} */ value) =>
    setState(current => current[key] === value ? current : { ...current, [key]: value }), []);
  const onToolChange = useCallback((/** @type {string} */ tool) => report('tool', tool), [report]);
  const onColorChange = useCallback((/** @type {string} */ color) => report('color', color), [report]);
  const onContentChange = useCallback((/** @type {boolean} */ hasContent) => report('hasContent', hasContent), [report]);
  const actions = useMemo(() => ({
    selectTool: (/** @type {import('./toolbar.jsx').DrawingTool} */ tool) => target.current?.setTool(tool),
    selectColor: (/** @type {string} */ color) => target.current?.setColor(color),
    undo: () => target.current?.undo(),
    redo: () => target.current?.redo(),
    clear: () => target.current?.clear(),
  }), []);
  return { ...state, ...actions, onReady, onToolChange, onColorChange, onContentChange };
}
