import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

/**
 * What a drawing toolbar needs of a mounted editor; `DrawingController` satisfies it.
 * @typedef {object} DrawingToolbarTarget
 * @property {(tool: import('./toolbar.jsx').DrawingTool) => void} setTool
 * @property {(color: string) => void} setColor
 * @property {(width: number) => void} setStrokeWidth
 * @property {() => void} undo
 * @property {() => void} redo
 * @property {() => void} clear
 */
/**
 * @typedef {object} DrawingSession
 * @property {boolean} ready
 * @property {string} tool
 * @property {string} color
 * @property {number} strokeWidth
 * @property {boolean} canUndo
 * @property {boolean} canRedo
 * @property {boolean} hasContent
 * @property {(tool: import('./toolbar.jsx').DrawingTool) => void} selectTool
 * @property {(color: string) => void} selectColor
 * @property {(width: number) => void} selectStrokeWidth
 * @property {() => void} undo
 * @property {() => void} redo
 * @property {() => void} clear
 * @property {(target: DrawingToolbarTarget | null) => void} onReady
 * @property {(tool: string) => void} onToolChange
 * @property {(color: string) => void} onColorChange
 * @property {(hasContent: boolean) => void} onContentChange
 * @property {(history: { canUndo: boolean, canRedo: boolean }) => void} onHistoryChange
 */

/**
 * One drawing session: a toolbar's view of the mounted editor and its only way
 * to drive it. The sketch itself lives in the editor; an inactive session (the
 * CAD Draw tool deselected) forgets the sketch, its history and the editor, as the
 * unmounted editor did — but not the tool, colour and weight in hand, which the
 * next session opens with.
 *
 * @param {boolean} [active]
 * @param {{ tool?: string, color?: string, strokeWidth?: number }} [initial]
 * @returns {DrawingSession}
 */
export function useDrawingSession(active = true, initial = {}) {
  const idle = useMemo(() => ({ ready: false, tool: initial.tool ?? 'selection', color: initial.color ?? '#1e1e1e', strokeWidth: initial.strokeWidth ?? 2,
    hasContent: false, canUndo: false, canRedo: false }), [initial.tool, initial.color, initial.strokeWidth]);
  const target = useRef(/** @type {DrawingToolbarTarget | null} */ (null));
  const [state, setState] = useState(idle);
  useEffect(() => {
    if (active) return;
    target.current = null;
    setState(current => ({ ...idle, tool: current.tool, color: current.color, strokeWidth: current.strokeWidth }));
  }, [active, idle]);
  const onReady = useCallback((/** @type {DrawingToolbarTarget | null} */ next) => {
    target.current = next;
    setState(current => next ? { ...current, ready: true } : { ...idle, tool: current.tool, color: current.color, strokeWidth: current.strokeWidth });
  }, [idle]);
  const report = useCallback((/** @type {'tool' | 'color' | 'hasContent'} */ key, /** @type {string | boolean} */ value) =>
    setState(current => current[key] === value ? current : { ...current, [key]: value }), []);
  const onToolChange = useCallback((/** @type {string} */ tool) => report('tool', tool), [report]);
  const onColorChange = useCallback((/** @type {string} */ color) => report('color', color), [report]);
  const onContentChange = useCallback((/** @type {boolean} */ hasContent) => report('hasContent', hasContent), [report]);
  const onHistoryChange = useCallback((/** @type {{ canUndo: boolean, canRedo: boolean }} */ history) =>
    setState(current => current.canUndo === history.canUndo && current.canRedo === history.canRedo
      ? current : { ...current, ...history }), []);
  const actions = useMemo(() => ({
    selectTool: (/** @type {import('./toolbar.jsx').DrawingTool} */ tool) => target.current?.setTool(tool),
    selectColor: (/** @type {string} */ color) => target.current?.setColor(color),
    // The editor reports tool and colour changes; the weight is only ever set from here.
    selectStrokeWidth: (/** @type {number} */ width) => { target.current?.setStrokeWidth(width); setState(current => current.strokeWidth === width ? current : { ...current, strokeWidth: width }); },
    undo: () => target.current?.undo(),
    redo: () => target.current?.redo(),
    clear: () => target.current?.clear(),
  }), []);
  return { ...state, ...actions, onReady, onToolChange, onColorChange, onContentChange, onHistoryChange };
}
