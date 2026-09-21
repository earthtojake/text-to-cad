import React, { useState } from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import FloatingToolBar from '../../../../../dist/renderers/cad/components/workbench/FloatingToolBar.js';

Object.assign(globalThis, { React });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function Harness() {
  const [tool, setTool] = useState('measure');
  const [filter, setFilter] = useState('all');
  return <FloatingToolBar selectedEntry={{ file: 'part.step' }} renderFormat="step" selectedMeshData={{}}
    selectionToolActive={tool === 'references'} measureModeActive={tool === 'measure'}
    handleSelectTabToolMode={setTool} selectionFilter={filter} onSelectionFilterChange={setFilter} />;
}

it('first activates Select, then opens its filter on a second press and restores focus on Escape', async () => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  const user = userEvent.setup();
  render(<Harness />);
  const select = screen.getByRole('button', { name: 'Select', exact: true });
  await user.click(select);
  expect(select.getAttribute('aria-pressed')).toBe('true');
  expect(screen.queryByRole('menu')).toBeNull();
  await user.click(select);
  expect(screen.getByRole('menu')).toBeTruthy();
  const choices = screen.getAllByRole('menuitemradio');
  await user.click(choices[1]);
  expect(select.getAttribute('aria-pressed')).toBe('true');
  expect(screen.queryByRole('menu')).toBeNull();
  await user.click(select);
  await user.keyboard('{Escape}');
  expect(document.activeElement).toBe(select);
  await user.click(screen.getByRole('button', { name: 'Measure', exact: true }));
  select.focus();
  await user.keyboard('{Enter}');
  expect(select.getAttribute('aria-pressed')).toBe('true');
  expect(screen.queryByRole('menu')).toBeNull();
  await user.keyboard('{Enter}');
  expect(screen.getByRole('menu')).toBeTruthy();
});

// The sub-toolbar reads left to right in the order a sketch is made: the marks
// first (Pen leading, because that is what Draw opens on), then the colour they
// are made in, then the two ways of moving around what was drawn, then undo/redo
// and Clear. This list IS that order.
const DRAWING_TOOL_LABELS = ['Pen', 'Line', 'Arrow', 'Rectangle', 'Ellipse', 'Text', 'Fill area', 'Eraser', 'Select and move drawings', 'Pan view'];
const DRAWING_BUTTON_LABELS = ['Pen', 'Line', 'Arrow', 'Rectangle', 'Ellipse', 'Text', 'Fill area', 'Eraser',
  'Color', 'Select and move drawings', 'Pan view', 'Undo', 'Redo', 'Clear drawing'];

function drawingSession(overrides = {}) {
  return { ready: true, tool: 'freedraw', color: '#ff2d55', hasContent: true, selectTool: vi.fn(), selectColor: vi.fn(), undo: vi.fn(), redo: vi.fn(), clear: vi.fn(), ...overrides };
}

function renderDrawToolbar(drawing, props = {}) {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  return render(<FloatingToolBar selectedEntry={{ file: 'part.step' }} renderFormat="step" selectedMeshData={{}}
    drawToolActive handleSelectTabToolMode={() => {}} drawing={drawing} {...props} />);
}

function drawingButtons() {
  const group = screen.getByRole('group', { name: 'Drawing tools' });
  return { group, buttons: [...group.querySelectorAll('button')] as HTMLButtonElement[] };
}

it('shows the drawing tools only while Draw is the active tool', () => {
  renderDrawToolbar(drawingSession(), { drawToolActive: false });
  expect(screen.queryByRole('group', { name: 'Drawing tools' })).toBeNull();
  cleanup();
  renderDrawToolbar(drawingSession());
  const { buttons } = drawingButtons();
  expect(buttons.map(button => button.getAttribute('aria-label'))).toEqual(DRAWING_BUTTON_LABELS);
  expect(screen.getByRole('button', { name: 'Draw', exact: true }).getAttribute('aria-pressed')).toBe('true');
});

it('presses exactly the tool the drawing editor reports', () => {
  renderDrawToolbar(drawingSession({ tool: 'arrow' }));
  const { buttons } = drawingButtons();
  const pressed = buttons.filter(button => button.getAttribute('aria-pressed') === 'true');
  expect(pressed.map(button => button.getAttribute('aria-label'))).toEqual(['Arrow']);
  for (const label of DRAWING_TOOL_LABELS.filter(name => name !== 'Arrow')) {
    expect(screen.getByRole('button', { name: label, exact: true }).getAttribute('aria-pressed')).toBe('false');
  }
});

it('keeps every drawing button disabled, and none pressed, until the editor is ready', async () => {
  const drawing = drawingSession({ ready: false });
  const user = userEvent.setup();
  renderDrawToolbar(drawing);
  const { buttons } = drawingButtons();
  expect(buttons).toHaveLength(DRAWING_BUTTON_LABELS.length);
  for (const button of buttons) {
    expect(button.disabled).toBe(true);
    expect(button.getAttribute('aria-pressed')).not.toBe('true');
    await user.click(button);
  }
  for (const action of [drawing.selectTool, drawing.undo, drawing.redo, drawing.clear]) expect(action).not.toHaveBeenCalled();
});

it('disables Clear drawing while there is nothing to clear, and nothing else', () => {
  renderDrawToolbar(drawingSession({ hasContent: false }));
  const { buttons } = drawingButtons();
  expect(buttons.filter(button => button.disabled).map(button => button.getAttribute('aria-label'))).toEqual(['Clear drawing']);
});

it('drives the drawing session: tool choice, undo, redo and clear', async () => {
  const drawing = drawingSession();
  const user = userEvent.setup();
  renderDrawToolbar(drawing);
  await user.click(screen.getByRole('button', { name: 'Arrow', exact: true }));
  expect(drawing.selectTool.mock.calls).toEqual([['arrow']]);
  await user.click(screen.getByRole('button', { name: 'Undo', exact: true }));
  await user.click(screen.getByRole('button', { name: 'Redo', exact: true }));
  await user.click(screen.getByRole('button', { name: 'Clear drawing', exact: true }));
  expect(drawing.undo).toHaveBeenCalledTimes(1);
  expect(drawing.redo).toHaveBeenCalledTimes(1);
  expect(drawing.clear).toHaveBeenCalledTimes(1);
  expect(drawing.selectTool).toHaveBeenCalledTimes(1);
});

it('offers the neon colors in the toolbar\'s own flow and sets only the color of what is drawn next', async () => {
  const drawing = drawingSession();
  const user = userEvent.setup();
  renderDrawToolbar(drawing);
  expect(screen.queryByRole('radiogroup', { name: 'Drawing color' })).toBeNull();
  await user.click(screen.getByRole('button', { name: 'Color', exact: true }));
  const colors = screen.getByRole('radiogroup', { name: 'Drawing color' });
  // No portal: the standalone editor keeps this strip light inside a dark application.
  expect(screen.getByRole('group', { name: 'Drawing tools' }).parentElement!.contains(colors)).toBe(true);
  const options = [...colors.querySelectorAll('[role="radio"]')];
  expect(options.map(option => option.getAttribute('aria-label'))).toEqual(['Neon red', 'Neon orange', 'Neon yellow', 'Neon green', 'Neon cyan', 'Electric blue', 'Neon magenta', 'White', 'Black']);
  expect(options.filter(option => option.getAttribute('aria-checked') === 'true').map(option => option.getAttribute('aria-label'))).toEqual(['Neon red']);
  await user.click(screen.getByRole('radio', { name: 'Neon green', exact: true }));
  expect(drawing.selectColor.mock.calls).toEqual([['#39ff14']]);
  expect(screen.queryByRole('radiogroup', { name: 'Drawing color' })).toBeNull();
  expect(drawing.selectTool).not.toHaveBeenCalled();
});

it('Measure takes up the tool on the first press and offers what it snaps to on the second, without toggling off', async () => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  const handleSelectTabToolMode = vi.fn(), onMeasureSnapFilterChange = vi.fn();
  const user = userEvent.setup();
  const props = { selectedEntry: { file: 'part.step' }, renderFormat: 'step', selectedMeshData: {}, measureSupported: true,
    handleSelectTabToolMode, measureSnapFilter: 'all', onMeasureSnapFilterChange, measurementPanel: <section aria-label="Measurements" /> };
  const view = render(<FloatingToolBar {...props} measureModeActive={false} />);
  await user.click(screen.getByRole('button', { name: 'Measure', exact: true }));
  expect(handleSelectTabToolMode.mock.calls).toEqual([['measure']]);
  expect(screen.queryByRole('menu')).toBeNull();
  expect(screen.queryByRole('region', { name: 'Measurements' })).toBeNull();

  view.rerender(<FloatingToolBar {...props} measureModeActive />);
  await user.click(screen.getByRole('button', { name: 'Measure', exact: true }));
  expect(handleSelectTabToolMode).toHaveBeenCalledTimes(1);
  await user.click(await screen.findByRole('menuitemradio', { name: /Edges/ }));
  expect(onMeasureSnapFilterChange).toHaveBeenCalledWith('edges');
  // A narrowed snap is named under the tools, as a narrowed selection filter is.
  view.rerender(<FloatingToolBar {...props} measureModeActive measureSnapFilter="edges" />);
  expect(screen.getByText('Edges', { exact: true })).toBeTruthy();
});

it('Animate is the rightmost tool, and exists only in a file that has routines', async () => {
  const handleSelectTabToolMode = vi.fn();
  const user = userEvent.setup();
  const props = { selectedEntry: { file: 'part.step' }, renderFormat: 'step', selectedMeshData: {}, measureSupported: true, handleSelectTabToolMode };
  const view = render(<FloatingToolBar {...props} />);
  const tools = () => [...screen.getByRole('group', { name: 'Interaction tools' }).querySelectorAll('button')].map(button => button.getAttribute('aria-label'));
  // Absent, never disabled: a model without animation has nothing to explain.
  expect(tools()).toEqual(['Select', 'Measure', 'Draw']);
  view.rerender(<FloatingToolBar {...props} animateAvailable />);
  expect(tools()).toEqual(['Select', 'Measure', 'Draw', 'Animate']);
  await user.click(screen.getByRole('button', { name: 'Animate', exact: true }));
  expect(handleSelectTabToolMode.mock.calls).toEqual([['animate']]);
  view.rerender(<FloatingToolBar {...props} animateAvailable animateToolActive />);
  expect(screen.getByRole('button', { name: 'Animate', exact: true }).getAttribute('aria-pressed')).toBe('true');
});

it('Pose exists only in a file with joints to drag, and sits left of Animate', async () => {
  const handleSelectTabToolMode = vi.fn();
  const user = userEvent.setup();
  const step = { selectedEntry: { file: 'part.step' }, renderFormat: 'step', selectedMeshData: {}, measureSupported: true, handleSelectTabToolMode };
  const view = render(<FloatingToolBar {...step} animateAvailable />);
  const tools = () => [...screen.getByRole('group', { name: 'Interaction tools' }).querySelectorAll('button')].map(button => button.getAttribute('aria-label'));
  // Absent, never disabled, like Animate.
  expect(tools()).toEqual(['Select', 'Measure', 'Draw', 'Animate']);
  view.rerender(<FloatingToolBar {...step} animateAvailable poseAvailable />);
  expect(tools()).toEqual(['Select', 'Measure', 'Draw', 'Pose', 'Animate']);
  view.rerender(<FloatingToolBar {...step} poseAvailable />);
  expect(tools()).toEqual(['Select', 'Measure', 'Draw', 'Pose']);
  await user.click(screen.getByRole('button', { name: 'Pose', exact: true }));
  expect(handleSelectTabToolMode.mock.calls).toEqual([['pose']]);
  view.rerender(<FloatingToolBar {...step} poseAvailable poseToolActive selectionToolActive={false} />);
  expect(screen.getByRole('button', { name: 'Pose', exact: true }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('button', { name: 'Select', exact: true }).getAttribute('aria-pressed')).toBe('false');
});
