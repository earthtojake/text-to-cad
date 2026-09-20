import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useDrawingSession } from './session.js';

afterEach(cleanup);
const editor = () => ({ setTool: vi.fn(), setColor: vi.fn(), undo: vi.fn(), redo: vi.fn(), clear: vi.fn() });
const CAD = { tool: 'freedraw', color: '#ff2d55' };

it('is the toolbar\'s view of the mounted editor and its only way to drive it', () => {
  const session = renderHook(({ active }) => useDrawingSession(active, CAD), { initialProps: { active: true } });
  expect(session.result.current).toMatchObject({ ready: false, tool: 'freedraw', color: '#ff2d55', hasContent: false });
  // Nothing is mounted yet: the toolbar's buttons are inert, not errors.
  act(() => { session.result.current.selectTool('arrow'); session.result.current.undo(); });

  const controller = editor();
  act(() => session.result.current.onReady(controller));
  expect(session.result.current.ready).toBe(true);
  act(() => { session.result.current.onToolChange('rectangle'); session.result.current.onColorChange('#39ff14'); session.result.current.onContentChange(true); });
  expect(session.result.current).toMatchObject({ tool: 'rectangle', color: '#39ff14', hasContent: true });

  act(() => { session.result.current.selectTool('arrow'); session.result.current.selectColor('#00e5ff'); session.result.current.undo(); session.result.current.redo(); session.result.current.clear(); });
  expect(controller.setTool).toHaveBeenCalledWith('arrow');
  expect(controller.setColor).toHaveBeenCalledWith('#00e5ff');
  expect([controller.undo, controller.redo, controller.clear].map(action => action.mock.calls.length)).toEqual([1, 1, 1]);
  // The editor, not the request, says which tool and color are active.
  expect(session.result.current).toMatchObject({ tool: 'rectangle', color: '#39ff14' });
});

it('keeps nothing of a sketch once Draw is left', () => {
  const session = renderHook(({ active }) => useDrawingSession(active, CAD), { initialProps: { active: true } });
  const controller = editor();
  act(() => { session.result.current.onReady(controller); session.result.current.onToolChange('text'); session.result.current.onColorChange('#ffffff'); session.result.current.onContentChange(true); });
  session.rerender({ active: false });
  expect(session.result.current).toMatchObject({ ready: false, tool: 'freedraw', color: '#ff2d55', hasContent: false });
  act(() => session.result.current.clear());
  expect(controller.clear).not.toHaveBeenCalled();
  // The editor releasing its controller on unmount is the same ending.
  session.rerender({ active: true });
  act(() => session.result.current.onReady(controller));
  act(() => session.result.current.onReady(null));
  expect(session.result.current.ready).toBe(false);
});

it('does not re-render the viewer for reports that change nothing', () => {
  const session = renderHook(() => useDrawingSession(true, CAD));
  act(() => session.result.current.onReady(editor()));
  const before = session.result.current;
  act(() => { session.result.current.onToolChange('freedraw'); session.result.current.onColorChange('#ff2d55'); session.result.current.onContentChange(false); });
  expect(session.result.current.tool).toBe(before.tool);
  expect(session.result.current.selectTool).toBe(before.selectTool);
  expect(session.result.current.onReady).toBe(before.onReady);
});
