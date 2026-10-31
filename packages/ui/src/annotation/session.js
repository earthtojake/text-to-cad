import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { sameView } from './views.js';
import { useViewerHistory } from '../renderers/kit/shell/useViewerHistory.js';
import { strokeWidthAt } from './geometry.js';
import { DEFAULT_PENCIL_TOOL, DEFAULT_SHAPE_TOOL, styleSlot, toolFamily } from './tools.js';
import { useControlUsage } from '../usage/controls.js';

// A drawing tool as telemetry names it (`usage/controls.js`): its strip tool's name, then its own.
const toolControl = tool => `${toolFamily(tool)}_${tool === 'freedraw' ? 'pen' : tool}`;

/**
 * @typedef {{ color: string, strokeWidth: number, placement: import('./toolbar.jsx').AnnotationPlacement }} DrawingStyle
 */

/**
 * The annotation: one annotation, its ink in the model (`renderers/kit/tools/annotate/annotation3d.js`'s items), what
 * the drawing tools put down next (`tool`, `style`) and its history. Pencil and Shapes, the two strip tools that
 * draw, share the ink and the history: each keeps the tool last chosen in it (`pencil`, `shape`), and `tool` is the
 * one of the strip tool in hand. The style is kept per drawing kind, three slots (`styles`): the pen, the highlighter
 * and Shapes (all five shapes share one), each with its own colour, stroke width and placement; `style` is the slot of
 * the tool in hand, and the eraser, which puts nothing down, has none (it shows the pen's, and sets nothing). It outlives the drawing tools being put down — the
 * ink stays in the model, and the next time one is taken up it draws on it — and goes when the person clears
 * it or the model it was drawn on changes (`discard`).
 * Each change to the ink is a step in the file view's one history (`useViewerHistory`), which
 * Undo and Redo walk whatever tool took the step.
 *
 * @typedef {object} AnnotationSession
 * @property {boolean} ready  Always: the toolbar's tools are the session's own.
 * @property {import('./tools.js').AnnotationTool} tool  The drawing tool in hand: Shapes' `shape` while Shapes is the strip tool,
 *   else Pencil's `pencil`.
 * @property {import('./tools.js').PencilTool} pencil  What Pencil draws with (the pen first), kept while Shapes is up.
 * @property {import('./tools.js').ShapeTool} shape  What Shapes draws with (the rectangle first), kept while Pencil is up.
 * @property {DrawingStyle} style  What the tool in hand puts down next: its slot's colour, stroke width and placement
 *   (`surface`, the default, each point on the visible surface under it, or `plane`, each on the plane of the surface the
 *   mark starts on; off the model both carry on at that plane: `annotation3d.js`'s `projectAnnotations`).
 * @property {Readonly<Record<import('./tools.js').StyleSlot, DrawingStyle>>} styles  Every slot's.
 * @property {readonly import('../renderers/kit/tools/annotate/annotation3d.js').AnnotationItem[]} items
 * @property {readonly string[]} selected  The ink the viewer's Select has picked: what the selection's bar
 *   (`restyle`, `fill`) and Delete act on. Annotate's tools never pick ink.
 * @property {boolean} canUndo
 * @property {boolean} canRedo
 * @property {boolean} hasContent  There is ink.
 * @property {boolean} hasAnnotation  The same: there is an annotation.
 * @property {(tool: import('./tools.js').AnnotationTool) => void} selectTool  Chooses what its strip tool draws with (Pencil's or Shapes'), a button of the sub-toolbar's row.
 * @property {(color: string) => void} selectColor  What the tool in hand draws next: its slot's, the others keep theirs.
 * @property {(width: number) => void} selectStrokeWidth  The same.
 * @property {(placement: import('./toolbar.jsx').AnnotationPlacement) => void} selectPlacement  The same: ink already down stays where it lies.
 * @property {(style: { color?: string, width?: number }) => void} restyle
 *   The ink selected, as one step: its colour, a stroke's weight (a shape's at that width, the pen's
 *   heavier, as each draws).
 * @property {(shape: string, areas: readonly import('../renderers/kit/tools/annotate/annotation3d.js').AnnotationItem[]) => void} fill
 *   A closed shape filled, as one step: the fill joins the shape's group, picked and deleted with it.
 * @property {(items: readonly import('../renderers/kit/tools/annotate/annotation3d.js').AnnotationItem[]) => void} add  Ink put down: one step.
 * @property {(ids: readonly string[]) => void} remove  Ink erased or deleted: one step.
 * @property {(ids: readonly string[]) => void} select
 * @property {() => void} undo
 * @property {() => void} redo
 * @property {() => void} clear  Every piece of ink, as one step to undo.
 * @property {() => void} forget  The same as `clear`.
 * @property {() => void} discard  Every piece of ink and the history with it, and the views: nothing to undo.
 * @property {readonly import('./views.js').LabelledView[]} views  The views ink was drawn in, in order
 *   ("view 1", "view 2"…): a mark names its own (`view`).
 * @property {(view: import('./views.js').PromptView | null) => string | undefined} noteView
 *   The label of the view ink is being put down in: the one drawn in before that is the same
 *   (`sameView`), or a new one.
 */

// The pen and Shapes open in the neon red; the highlighter in the palette's neon yellow (`ANNOTATION_COLORS`), as a highlighter is.
const DEFAULT_STYLES = Object.freeze({
  pen: Object.freeze({ color: '#ff2d55', strokeWidth: 2, placement: 'surface' }),
  highlighter: Object.freeze({ color: '#ffe600', strokeWidth: 2, placement: 'surface' }),
  shapes: Object.freeze({ color: '#ff2d55', strokeWidth: 2, placement: 'surface' }),
});
const SLOTS = Object.keys(DEFAULT_STYLES);
const NO_ANNOTATIONS = Object.freeze([]);

/**
 * @param {import('./tools.js').AnnotationFamily | null} [family]  The drawing strip tool in hand, Pencil or Shapes; none while another
 *   tool is. Put down, the ink, its selection, what each draws with, the colour, the weight and the placement stay.
 * @param {{ pencil?: string, shape?: string,
 *   styles?: Partial<Record<import('./tools.js').StyleSlot, Partial<DrawingStyle>>> }} [initial]  Where it opens: what
 *   each strip tool draws with, and any of each slot's style over the defaults.
 * @param {import('../renderers/kit/shell/useViewerHistory.js').ViewerHistory | null} [history]  The file
 *   view's; without one the session keeps its own.
 * @returns {AnnotationSession}
 */
export function useAnnotationSession(family = 'pencil', initial = {}, history = null) {
  const start = useMemo(() => ({
    pencil: initial.pencil ?? DEFAULT_PENCIL_TOOL,
    shape: initial.shape ?? DEFAULT_SHAPE_TOOL,
    styles: Object.fromEntries(SLOTS.map(slot => [slot, { ...DEFAULT_STYLES[slot],
      ...Object.fromEntries(Object.entries(initial.styles?.[slot] ?? {}).filter(([, value]) => value != null)) }])),
  }), [initial.pencil, initial.shape, initial.styles]);
  const [pencil, setPencil] = useState(start.pencil);
  const [shape, setShape] = useState(start.shape);
  const [styles, setStyles] = useState(start.styles);
  const own = useViewerHistory();
  const log = history ?? own;
  const logRef = useRef(log);
  logRef.current = log;
  // The ink; each step records the ink before and after it, so Undo and Redo put either back.
  const [items, setItems] = useState(/** @type {readonly import('../renderers/kit/tools/annotate/annotation3d.js').AnnotationItem[]} */ (NO_ANNOTATIONS));
  const itemsRef = useRef(items);
  const [selected, setSelected] = useState(/** @type {string[]} */ ([]));
  // The views ink was drawn in. Not a step to undo: a label a mark names stays, whatever is undone.
  const viewsRef = useRef(/** @type {import('./views.js').LabelledView[]} */ ([]));
  const [views, setViews] = useState(viewsRef.current);
  const noteView = useCallback(view => {
    if (!view) return undefined;
    const known = viewsRef.current.findLast(drawn => sameView(drawn, view));
    if (known) return known.label;
    const label = `view ${viewsRef.current.length + 1}`;
    viewsRef.current = [...viewsRef.current, { ...view, label }];
    setViews(viewsRef.current);
    return label;
  }, []);
  const put = useCallback(next => { itemsRef.current = next; setItems(next); }, []);
  const step = useCallback(change => {
    const before = itemsRef.current;
    const after = change(before);
    if (after === before) return;
    put(after);
    logRef.current.record({ source: 'annotation', undo: () => put(before), redo: () => put(after) });
  }, [put]);
  // Ink an undo took away takes its pick with it.
  useEffect(() => {
    setSelected(current => (current.every(id => items.some(item => item.id === id)) ? current
      : current.filter(id => items.some(item => item.id === id))));
  }, [items]);
  // What a person did to the ink, counted (`usage/controls.js`): a mark put down, ink deleted, a style chosen.
  const controls = useControlUsage();
  const add = useCallback(items => { if (items.length) { controls.used('annotate_mark'); step(current => [...current, ...items]); } }, [step, controls]);
  const remove = useCallback(ids => {
    const gone = new Set(ids);
    if (!gone.size) return;
    controls.used('annotate_delete');
    step(current => (current.some(item => gone.has(item.id)) ? current.filter(item => !gone.has(item.id)) : current));
    setSelected(current => current.filter(id => !gone.has(id)));
  }, [step, controls]);
  const selectedRef = useRef(selected);
  selectedRef.current = selected;
  const tool = family === 'shapes' ? shape : pencil;
  const slot = styleSlot(tool);
  const slotRef = useRef(slot);
  slotRef.current = slot;
  // A style is set on the slot of the tool in hand, whichever it is when the change is made; the eraser has none.
  const setStyle = useCallback(change => {
    const target = slotRef.current;
    if (target) setStyles(current => (Object.entries(change).every(([key, value]) => current[target][key] === value) ? current
      : { ...current, [target]: { ...current[target], ...change } }));
  }, []);
  const actions = useMemo(() => ({
    selectTool: next => { controls.used(toolControl(next)); return toolFamily(next) === 'shapes' ? setShape(next) : setPencil(next); },
    selectColor: next => { controls.changed('annotate_color'); setStyle({ color: next }); },
    selectStrokeWidth: next => { controls.used('annotate_stroke_width'); setStyle({ strokeWidth: next }); },
    selectPlacement: next => { controls.used(next === 'plane' ? 'annotate_on_plane' : 'annotate_on_surface'); setStyle({ placement: next }); },
    // Not a style: ink already down, selected or not, stays where it lies.
    restyle: ({ color: nextColor, width }) => {
      const ids = new Set(selectedRef.current);
      if (!ids.size) return;
      controls.changed('annotate_restyle');
      step(current => {
        let changed = false;
        const next = current.map(item => {
          if (!ids.has(item.id)) return item;
          const styled = { ...item };
          if (nextColor != null && item.color !== nextColor) styled.color = nextColor;
          if (width != null && item.kind === 'stroke') {
            // The pen's own weight is heavier than a shape's at the same setting, the highlighter's broad (`geometry.js`).
            const drawn = strokeWidthAt(item, width);
            if (item.width !== drawn) styled.width = drawn;
          }
          if (Object.keys(styled).some(key => styled[key] !== item[key])) { changed = true; return styled; }
          return item;
        });
        return changed ? next : current;
      });
    },
    fill: (shape, areas) => {
      if (!areas.length) return;
      controls.used('annotate_fill');
      step(current => {
        const target = current.find(item => item.id === shape);
        if (!target) return current;
        const group = target.group ?? `group-${shape}`;
        return [...current.map(item => (item.id === shape && !item.group ? { ...item, group } : item)),
          ...areas.map(area => ({ ...area, group, color: target.color }))];
      });
      // A picked shape's fill is picked with it, as its group is.
      setSelected(current => (current.includes(shape) ? [...current, ...areas.map(area => area.id)] : current));
    },
    select: ids => setSelected([...ids]),
    undo: () => { logRef.current.undo(); },
    redo: () => { logRef.current.redo(); },
    clear: () => { step(current => (current.length ? NO_ANNOTATIONS : current)); setSelected([]); },
    discard: () => {
      put(NO_ANNOTATIONS);
      logRef.current.forget('annotation');
      setSelected([]);
      viewsRef.current = [];
      setViews([]);
    },
  }), [step, put, setStyle, controls]);
  const hasContent = items.length > 0;
  return { ready: true, tool, pencil, shape, style: styles[slot ?? 'pen'], styles, items, selected, views,
    canUndo: log.canUndo, canRedo: log.canRedo, hasContent, hasAnnotation: hasContent,
    add, remove, noteView, forget: actions.clear, ...actions };
}
