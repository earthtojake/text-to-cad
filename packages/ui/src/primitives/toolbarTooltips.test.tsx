import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { Files } from 'lucide-react';
import { ToolbarButton } from '../../dist/primitives/toolbar-button.js';
import { PanelToggle } from '../../dist/file-viewer/navigation/FileNavRow.js';
import FloatingToolBar from '../../dist/renderers/kit/tools/FloatingToolBar.js';
import PreviewChrome from '../../dist/renderers/kit/tools/PreviewChrome.js';

// The viewer's hints: the strip's tools, the nav row's panel toggles and the top-right bar all
// hint through one primitive (`tooltip.jsx`), after a deliberate hover, never sticking after a press.
beforeEach(() => { vi.useFakeTimers(); vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
const tip = () => screen.queryByRole('tooltip');
const enter = (node: Element) => fireEvent.pointerMove(node, { pointerType: 'mouse' });
const wait = (ms: number) => act(() => { vi.advanceTimersByTime(ms); });
const strip = (active = '') => <FloatingToolBar tools={['Draw', 'Measure', 'Select'].map(label => ({ id: label, label, active: label === active, icon: <span>{label[0]}</span>, onSelect() {} }))} />;

it('a tool is hinted only after a deliberate hover, with the same delay from one tool to the next, and a press dismisses it for good', () => {
  const { rerender } = render(strip());
  const draw = screen.getByRole('button', { name: 'Draw' }), measure = screen.getByRole('button', { name: 'Measure' });
  enter(draw);
  wait(150);
  expect(tip()).toBeNull();
  wait(300);
  expect(tip()!.textContent).toBe('Draw');
  // Leaving toward the tip dismisses it: the hint is no hover bridge (`disableHoverableContent`).
  fireEvent.pointerLeave(draw, { pointerType: 'mouse' });
  wait(0);
  expect(tip()).toBeNull();
  // Moving on to the next tool: the same wait, no instant hand-over.
  enter(measure);
  wait(150);
  expect(screen.queryByRole('tooltip', { name: 'Measure' })).toBeNull();
  wait(300);
  expect(tip()!.textContent).toBe('Measure');
  fireEvent.pointerDown(measure);
  fireEvent.click(measure);
  expect(tip()).toBeNull();
  // Measure is the tool now: pressed, it hints nothing; a second press does not bring the tip back.
  rerender(strip('Measure'));
  wait(500);
  expect(tip()).toBeNull();
  fireEvent.pointerDown(measure);
  fireEvent.click(measure);
  rerender(strip());
  wait(500);
  expect(tip()).toBeNull();
});

it('the nav row, the strip and the top-right bar share one hint with no native title; a click that focuses a trigger pins nothing, a Tab onto it names it', () => {
  render(<>
    <PanelToggle icon={Files} label="Show files" active={false} onClick={() => {}} id="tree" />
    {strip()}
    <ToolbarButton label="Display settings">D</ToolbarButton>
    <ToolbarButton label="Preview">P</ToolbarButton>
  </>);
  const classes: string[] = [];
  for (const [name, hint] of [['Show files', 'Files'], ['Draw', 'Draw'], ['Display settings', 'Display settings'], ['Preview', 'Preview']]) {
    const button = screen.getByRole('button', { name });
    expect(button.hasAttribute('title')).toBe(false);
    enter(button);
    wait(450);
    expect(tip()!.textContent, name).toBe(hint);
    classes.push(document.querySelector('[data-slot=tooltip-content]')!.className);
    fireEvent.pointerLeave(button, { pointerType: 'mouse' });
    fireEvent.pointerDown(document.body);
    wait(50);
  }
  expect(new Set(classes).size).toBe(1);
  expect(document.querySelectorAll('[title]').length).toBe(0);
  // A press focuses the trigger: no hint comes with that focus.
  const display = screen.getByRole('button', { name: 'Display settings' });
  fireEvent.pointerDown(display);
  act(() => display.focus());
  wait(500);
  expect(tip()).toBeNull();
  // Tabbing IS navigation: the control a Tab lands on names itself.
  const preview = screen.getByRole('button', { name: 'Preview' });
  fireEvent.keyDown(document.activeElement!, { key: 'Tab' });
  const focusVisible = vi.spyOn(preview, 'matches').mockImplementation(function (this: Element, selector: string) {
    return selector === ':focus-visible' ? true : Element.prototype.matches.call(this, selector);
  });
  act(() => preview.focus());
  wait(10);
  expect(tip()!.textContent).toBe('Preview');
  focusVisible.mockRestore();
});

it('preview puts the editor tools and their hints away', () => {
  const { rerender } = render(<PreviewChrome active={false}>{strip()}</PreviewChrome>);
  const draw = screen.getByRole('button', { name: 'Draw' });
  enter(draw);
  wait(450);
  expect(tip()!.textContent).toBe('Draw');
  rerender(<PreviewChrome active>{strip()}</PreviewChrome>);
  wait(500);
  expect(tip()).toBeNull();
  enter(draw);
  wait(500);
  expect(tip()).toBeNull();
});
