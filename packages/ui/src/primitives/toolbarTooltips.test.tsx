import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { ToolbarButton } from '../../dist/primitives/toolbar-button.js';
import FloatingToolBar from '../../dist/renderers/kit/tools/FloatingToolBar.js';
import PreviewChrome from '../../dist/renderers/kit/tools/PreviewChrome.js';

// The viewer's hints: the strip's tools and the view's actions hint through one primitive
// (`tooltip.jsx`), after a deliberate hover, never sticking after a press.
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

it('the strip and the view\'s actions share one hint with no native title; a click that focuses a trigger pins nothing, a Tab onto it names it, and focus moved by code after that Tab names nothing', () => {
  render(<>
    {strip()}
    <ToolbarButton label="Display">D</ToolbarButton>
    <ToolbarButton label="Preview">P</ToolbarButton>
  </>);
  const classes: string[] = [];
  for (const [name, hint] of [['Draw', 'Draw'], ['Display', 'Display'], ['Preview', 'Preview']]) {
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
  const display = screen.getByRole('button', { name: 'Display' });
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
  // That Tab is spent on the move it made: focus code hands over later (a peek going from under the keyboard) names
  // nothing, focus-visible as it is.
  const draw = screen.getByRole('button', { name: 'Draw' });
  const visible = vi.spyOn(draw, 'matches').mockImplementation(function (this: Element, selector: string) {
    return selector === ':focus-visible' ? true : Element.prototype.matches.call(this, selector);
  });
  act(() => draw.focus());
  wait(500);
  expect(tip()).toBeNull();
  visible.mockRestore();
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

// In the dark a toolbar's fills are its own: the base Button's ghost hover (`dark:hover:bg-accent/50`, which outranks a
// plain `hover:` and matched the surface) never reaches a toolbar button or a split tool's.
it("a toolbar button's fills win over the base Button's ghost hover in the dark: a tile and a split tool's button", async () => {
  const classes = (element: Element) => element.className.split(/\s+/);
  const { container, unmount } = render(<>
    <ToolbarButton label="Tile" tooltip={false} />
    <FloatingToolBar tools={[{ id: 'select', label: 'Select', icon: null, onSelect() {}, menu: 'MENU' }]} />
  </>);
  const tile = classes(container.querySelector('[aria-label="Tile"]')!);
  expect([tile.includes('dark:hover:bg-accent/50'), tile.includes('dark:hover:bg-foreground/10'), tile.includes('dark:data-[variant=secondary]:bg-foreground/16')]).toEqual([false, true, true]);
  const split = container.querySelector('[data-tool-split]')!;
  const inner = classes(split.querySelector('button')!);
  expect([classes(split).includes('dark:hover:bg-foreground/10'), inner.includes('dark:hover:bg-transparent'), inner.includes('dark:hover:bg-foreground/10'), inner.includes('dark:hover:bg-accent/50')])
    .toEqual([true, true, false, false]);
  unmount();
});
