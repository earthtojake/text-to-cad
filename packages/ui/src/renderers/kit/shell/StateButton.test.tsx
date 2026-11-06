import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ArrowUpToLine, Square } from 'lucide-react';
import StateButton from '../../../../dist/renderers/kit/shell/StateButton.js';
import ProjectionToggle from '../../../../dist/renderers/kit/shell/ProjectionToggle.js';

// The view's one state button (`StateButton.jsx`), Projection's and a view's own: its icon is the state
// on screen, its name says that state, its tooltip what a press does, with the key that does the same;
// lit, it is drawn in the strip's pressed fill and keeps its tooltip, which a tool in hand does not.
beforeEach(() => { vi.useFakeTimers(); vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
const tip = () => screen.queryByRole('tooltip');
// A deliberate hover: past the hints' 400ms delay.
const hover = (node: Element) => { fireEvent.pointerMove(node, { pointerType: 'mouse' }); act(() => { vi.advanceTimersByTime(450); }); };
const away = (node: Element) => { fireEvent.pointerLeave(node, { pointerType: 'mouse' }); act(() => { vi.advanceTimersByTime(10); }); };
const icon = (button: HTMLElement) => [...button.querySelector('svg')!.classList].find(name => name.startsWith('lucide-'));

it('shows the state on screen and names it; its tooltip says what a press does, with its key; it is a plain button', () => {
  const presses: string[] = [];
  render(<StateButton icon={Square} label="View: 2D" tooltip="Switch to 3D" shortcut="3" onPress={() => presses.push('pressed')} data-view-state="2d" />);
  const button = screen.getByRole('button', { name: 'View: 2D' });
  expect(icon(button)).toBe('lucide-square');
  // Its name changes with the state, so it is no toggle: no aria-pressed (the APG button pattern).
  expect(button.hasAttribute('aria-pressed')).toBe(false);
  expect([button.getAttribute('aria-keyshortcuts'), button.getAttribute('data-variant'), button.getAttribute('data-view-state')]).toEqual(['3', 'ghost', '2d']);
  expect(button.hasAttribute('data-state-button')).toBe(true);
  // A strip tile: 24px, its icon 14px.
  expect(button.className).toContain('size-6');
  expect(button.className).toContain('[&>svg]:size-3.5!');
  hover(button);
  expect(tip()!.textContent).toBe('Switch to 3D3');
  expect(document.querySelector('[data-slot=tooltip-content] [data-tooltip-shortcut]')!.textContent).toBe('3');
  away(button);
  fireEvent.click(button);
  expect(presses).toEqual(['pressed']);
});

it('lit for a state a person may lose track of, it is drawn in the pressed fill and still says what a press does', () => {
  render(<StateButton icon={ArrowUpToLine} label="Side: Bottom" tooltip="View from top" shortcut="⇧F" lit onPress={() => {}} />);
  const button = screen.getByRole('button', { name: 'Side: Bottom' });
  expect(icon(button)).toBe('lucide-arrow-up-to-line');
  expect([button.getAttribute('data-variant'), button.getAttribute('aria-keyshortcuts'), button.hasAttribute('aria-pressed')]).toEqual(['secondary', 'Shift+F', false]);
  hover(button);
  expect(tip()!.textContent).toBe('View from top⇧F');
});

it('Projection is the state button: the projection on screen, named, the other one its tooltip, a press switching to it', () => {
  let projection = 'orthographic';
  const { rerender } = render(<ProjectionToggle projection={{ value: projection, onChange: (next: string) => { projection = next; } }} />);
  const button = screen.getByRole('button', { name: 'Projection: Orthographic' });
  expect([button.hasAttribute('data-state-button'), button.getAttribute('data-projection'), button.hasAttribute('aria-pressed')]).toEqual([true, 'orthographic', false]);
  hover(button);
  expect(tip()!.textContent).toBe('Switch to Perspective');
  away(button);
  fireEvent.click(button);
  expect(projection).toBe('perspective');
  rerender(<ProjectionToggle projection={{ value: projection, onChange: (next: string) => { projection = next; } }} />);
  expect(screen.getByRole('button', { name: 'Projection: Perspective' })).toBe(button);
  expect(button.getAttribute('data-projection')).toBe('perspective');
});
