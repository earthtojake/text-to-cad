import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { useAnnotationSession } from './session.js';
import { CAD_ANNOTATION_DEFAULTS } from '../renderers/kit/tools/annotate/AnnotationOverlay.jsx';
import { annotationColors } from './toolbar.jsx';
import { useViewerHistory } from '../renderers/kit/shell/useViewerHistory.js';

afterEach(cleanup);
const CAD = CAD_ANNOTATION_DEFAULTS;
const stroke = (id: string, extra = {}) => ({ id, kind: 'stroke', points: new Float32Array(6), color: '#ff2d55', width: 2, ...extra });
const view = (x: number) => ({ camera: { position: [x, -100, 0], target: [0, 0, 0], up: [0, 0, 1], orthographicHalfHeight: 50 }, width: 1600, height: 1200 });

it('holds the ink, each add, erase or restyle one step to undo and redo; clear is one more, discard leaves nothing to undo', () => {
  const session = renderHook(() => useAnnotationSession('pencil', CAD));
  const current = () => session.result.current;
  expect(current()).toMatchObject({ ready: true, tool: 'freedraw', pencil: 'freedraw', shape: 'rectangle', style: { color: '#ff2d55', strokeWidth: 2, placement: 'surface' }, hasContent: false });
  act(() => current().add([stroke('a'), stroke('b')]));
  act(() => current().remove(['a']));
  act(() => current().select(['b']));
  act(() => current().restyle({ color: '#00e5ff' }));
  expect(current().items.map(item => [item.id, item.color])).toEqual([['b', '#00e5ff']]);
  act(() => current().undo());
  act(() => current().undo());
  expect(current().items.map(item => item.id)).toEqual(['a', 'b']);
  act(() => current().redo());
  expect(current().items.map(item => item.id)).toEqual(['b']);
  act(() => current().clear());
  expect(current()).toMatchObject({ hasContent: false, canUndo: true });
  act(() => current().undo());
  expect(current().hasAnnotation).toBe(true);
  act(() => current().discard());
  expect(current()).toMatchObject({ hasContent: false, canUndo: false, canRedo: false });
});

it("the colour and weight are what is drawn next; the selection's restyle is one step, the pen's weight its own and the highlighter's five times", () => {
  const session = renderHook(() => useAnnotationSession('pencil', CAD));
  const current = () => session.result.current;
  act(() => current().add([stroke('a'), stroke('b'), stroke('p', { widths: [1, 1] }), stroke('h', { width: 10, opacity: 0.35 })]));
  act(() => current().select(['a', 'p', 'h']));
  act(() => { current().selectColor('#39ff14'); current().selectStrokeWidth(4); });
  expect(current()).toMatchObject({ style: { color: '#39ff14', strokeWidth: 4 }, canUndo: true });
  expect(current().items.map(item => item.color)).toEqual(['#ff2d55', '#ff2d55', '#ff2d55', '#ff2d55']);
  act(() => current().restyle({ color: '#ffffff', width: 4 }));
  expect(current().items.map(item => [item.id, item.color, item.width])).toEqual([
    ['a', '#ffffff', 4], ['b', '#ff2d55', 2], ['p', '#ffffff', 6], ['h', '#ffffff', 20]]);
  act(() => current().undo());
  expect(current().items.map(item => item.color)).toEqual(['#ff2d55', '#ff2d55', '#ff2d55', '#ff2d55']);
});

it("a fill joins its shape's group in its colour, one step; an undo takes the pick of ink it removes", () => {
  const session = renderHook(() => useAnnotationSession('pencil', CAD));
  const current = () => session.result.current;
  act(() => current().add([stroke('r', { closed: true, color: '#00e5ff' })]));
  act(() => current().fill('r', [{ id: 'f', kind: 'area', points: new Float32Array(9), color: '#ff2d55' } as any]));
  const [shape, fill] = current().items;
  expect(fill).toMatchObject({ id: 'f', color: '#00e5ff', group: shape.group });
  expect(shape.group).toBeTruthy();
  act(() => current().select(['r', 'f']));
  act(() => current().undo());
  expect(current().items.map(item => item.id)).toEqual(['r']);
  expect(current().selected).toEqual(['r']);
});

it("shares the file view's history: Undo walks the steps of every tool in the order they were taken", () => {
  const shared = renderHook(() => {
    const history = useViewerHistory();
    return { history, session: useAnnotationSession('pencil', CAD, history) };
  });
  const current = () => shared.result.current;
  const other: string[] = [];
  act(() => current().session.add([stroke('a')]));
  act(() => current().history.record({ source: 'measure', undo: () => other.push('undo'), redo: () => other.push('redo') }));
  act(() => current().session.add([stroke('b')]));
  act(() => { current().history.undo(); });
  act(() => { current().history.undo(); });
  expect([current().session.items.map(item => item.id), other]).toEqual([['a'], ['undo']]);
  act(() => { current().history.redo(); });
  expect(other).toEqual(['undo', 'redo']);
  // An annotation discarded takes only its own steps out.
  act(() => current().session.discard());
  expect(current().history).toMatchObject({ canUndo: true, canRedo: false });
  act(() => { current().history.undo(); });
  expect(other).toEqual(['undo', 'redo', 'undo']);
  expect(current().history.canUndo).toBe(false);
});

it('names the view ink goes down in: one drawn in before that is the same, or a new one; discard forgets them', () => {
  const session = renderHook(() => useAnnotationSession('pencil', CAD));
  const current = () => session.result.current;
  let labels: (string | undefined)[] = [];
  act(() => { labels = [current().noteView(view(0)), current().noteView(view(1)), current().noteView(view(100)), current().noteView(null)]; });
  expect(labels).toEqual(['view 1', 'view 1', 'view 2', undefined]);
  expect(current().views.map(entry => entry.label)).toEqual(['view 1', 'view 2']);
  act(() => current().discard());
  expect(current().views).toEqual([]);
});

it('keeps only the views\' labels: no plane, and none to look up', () => {
  const session = renderHook(() => useAnnotationSession('pencil', CAD));
  act(() => { session.result.current.noteView(view(0)); });
  expect(session.result.current.views[0]).not.toHaveProperty('plane');
  expect(session.result.current).not.toHaveProperty('planeOf');
});

it('Placement is what is drawn next: on the surface at first, kept like the colour when the drawing tools are put down', () => {
  const session = renderHook(({ family }) => useAnnotationSession(family, CAD), { initialProps: { family: 'pencil' as 'pencil' | 'shapes' | null } });
  const current = () => session.result.current;
  expect(current().style.placement).toBe('surface');
  act(() => current().selectPlacement('plane'));
  session.rerender({ family: null });
  expect(current().style.placement).toBe('plane');
});

it('Pencil and Shapes each keep what they draw with — the pen and the rectangle first — and share the ink, not the style', () => {
  const session = renderHook(({ family }) => useAnnotationSession(family, CAD), { initialProps: { family: 'shapes' as 'pencil' | 'shapes' | null } });
  const current = () => session.result.current;
  // Shapes is up: its tool in hand is the rectangle.
  expect(current()).toMatchObject({ tool: 'rectangle', pencil: 'freedraw', shape: 'rectangle' });
  act(() => { current().selectColor('#39ff14'); current().selectStrokeWidth(4); current().selectPlacement('plane'); });
  // Choosing in Pencil's menu (a pencil tool) leaves Shapes' choice alone, and Pencil takes it up.
  act(() => current().selectTool('highlighter'));
  expect(current()).toMatchObject({ tool: 'rectangle', pencil: 'highlighter', shape: 'rectangle' });
  session.rerender({ family: 'pencil' });
  // The highlighter's own style, not Shapes'.
  expect(current()).toMatchObject({ tool: 'highlighter', style: { color: '#ffe600', strokeWidth: 2, placement: 'surface' } });
  act(() => current().selectTool('ellipse'));
  expect(current()).toMatchObject({ tool: 'highlighter', pencil: 'highlighter', shape: 'ellipse' });
  session.rerender({ family: 'shapes' });
  expect(current()).toMatchObject({ tool: 'ellipse', style: { color: '#39ff14', strokeWidth: 4, placement: 'plane' } });
});

it('style is kept per drawing kind: the pen, the highlighter and Shapes (all five shapes) each have a colour, weight and placement, set on the slot of the tool in hand', () => {
  const session = renderHook(({ family }) => useAnnotationSession(family, CAD), { initialProps: { family: 'pencil' as 'pencil' | 'shapes' | null } });
  const current = () => session.result.current;
  const slots = () => Object.fromEntries(Object.entries(current().styles).map(([slot, style]) => [slot, [style.color, style.strokeWidth, style.placement]]));
  expect(slots()).toEqual({ pen: ['#ff2d55', 2, 'surface'], highlighter: ['#ffe600', 2, 'surface'], shapes: ['#ff2d55', 2, 'surface'] });
  act(() => { current().selectColor('#00e5ff'); current().selectStrokeWidth(6); });
  act(() => current().selectTool('highlighter'));
  expect(current().style).toEqual({ color: '#ffe600', strokeWidth: 2, placement: 'surface' });
  act(() => current().selectPlacement('plane'));
  session.rerender({ family: 'shapes' });
  act(() => current().selectStrokeWidth(4));
  act(() => current().selectTool('arrow'));
  expect(current().style).toEqual({ color: '#ff2d55', strokeWidth: 4, placement: 'surface' });
  expect(slots()).toEqual({ pen: ['#00e5ff', 6, 'surface'], highlighter: ['#ffe600', 2, 'plane'], shapes: ['#ff2d55', 4, 'surface'] });
  // A selection's restyle restyles that ink only, no slot.
  act(() => current().add([stroke('a')]));
  act(() => current().select(['a']));
  act(() => current().restyle({ color: '#ffffff', width: 6 }));
  expect(slots()).toEqual({ pen: ['#00e5ff', 6, 'surface'], highlighter: ['#ffe600', 2, 'plane'], shapes: ['#ff2d55', 4, 'surface'] });
  expect(current().items[0]).toMatchObject({ color: '#ffffff', width: 6 });
});

it('the Eraser has no style: it shows the pen\'s and sets nothing', () => {
  const session = renderHook(() => useAnnotationSession('pencil', CAD));
  const current = () => session.result.current;
  act(() => current().selectTool('eraser'));
  act(() => { current().selectColor('#ffffff'); current().selectStrokeWidth(6); current().selectPlacement('plane'); });
  expect(current().styles).toEqual(renderHook(() => useAnnotationSession('pencil', CAD)).result.current.styles);
  expect(current().style).toBe(current().styles.pen);
});

it("the highlighter's default colour is on the palette in both colour schemes", () => {
  const session = renderHook(() => useAnnotationSession('pencil', CAD));
  for (const scheme of ['light', 'dark'] as const) {
    expect(annotationColors(scheme).map(option => option.value)).toContain(session.result.current.styles.highlighter.color);
  }
});

it("put down, the drawing tools keep what each draws with, the ink, Select's pick of it", () => {
  const session = renderHook(({ family }) => useAnnotationSession(family, CAD), { initialProps: { family: 'pencil' as 'pencil' | 'shapes' | null } });
  const current = () => session.result.current;
  act(() => { current().add([stroke('a')]); current().selectTool('eraser'); current().select(['a']); });
  session.rerender({ family: null });
  expect(current()).toMatchObject({ pencil: 'eraser', selected: ['a'], hasAnnotation: true });
});
