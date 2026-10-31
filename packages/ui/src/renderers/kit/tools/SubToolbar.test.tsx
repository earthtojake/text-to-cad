import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import SubToolbar, { SubToolbarSeparator, rowsOf } from '../../../../dist/renderers/kit/tools/SubToolbar.js';
import { StripTouchProvider } from '../../../../dist/renderers/kit/tools/stripTouch.js';

// jsdom lays nothing out: each child says its own top (`data-top`), as the browser's layout would.
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  Object.defineProperty(HTMLElement.prototype, 'offsetTop', { configurable: true, get() { return Number(this.getAttribute('data-top') || 0); } });
  Object.defineProperty(HTMLElement.prototype, 'offsetHeight', { configurable: true, get() { return 36; } });
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  delete (HTMLElement.prototype as any).offsetTop;
  delete (HTMLElement.prototype as any).offsetHeight;
});

const row = (tops: number[], touch: boolean) => render(<StripTouchProvider value={touch}>
  <SubToolbar label="Drawing controls">
    <div role="group" aria-label="Shapes tools" data-top={tops[0]}><button type="button">Rectangle</button></div>
    <SubToolbarSeparator />
    <div role="group" aria-label="Annotation style" data-top={tops[1]}><button type="button">Color</button></div>
  </SubToolbar>
</StripTouchProvider>);

it('counts the lines a wrapping row stands on from its children\'s tops, the undrawn ones left out', () => {
  const child = (offsetTop: number, drawn = true) => ({ offsetTop, offsetWidth: drawn ? 36 : 0, offsetHeight: drawn ? 36 : 0 });
  expect(rowsOf({ children: [child(0), child(0), child(0)] })).toBe(1);
  expect(rowsOf({ children: [child(0), child(0), child(44)] })).toBe(2);
  expect(rowsOf({ children: [child(0), child(44, false)] })).toBe(1);
  expect(rowsOf(null)).toBe(0);
});

// On a phone Shapes' row is wider than the view and wraps: its style group stands under its tools,
// and the rule that parted them side by side would dangle at the first line's end.
it('a phone\'s row that wrapped draws no rule between its groups, and one on one line keeps it', () => {
  const { container } = row([0, 44], true);
  const toolbar = container.querySelector('[data-cad-sub-toolbar]')!;
  const rule = container.querySelector('[data-sub-toolbar-rule]')!;
  expect([toolbar.hasAttribute('data-wrapped'), rule.hasAttribute('data-hidden'), rule.className.includes('invisible')]).toEqual([true, true, true]);
  cleanup();
  const flat = row([0, 0], true);
  expect([flat.container.querySelector('[data-cad-sub-toolbar]')!.hasAttribute('data-wrapped'), flat.container.querySelector('[data-sub-toolbar-rule]')!.hasAttribute('data-hidden')]).toEqual([false, false]);
  cleanup();
  // A desktop's row never wraps (Shapes' is one line, `flex-nowrap`): no measure, the rule stays.
  const desktop = row([0, 44], false);
  expect([desktop.container.querySelector('[data-cad-sub-toolbar]')!.hasAttribute('data-wrapped'), desktop.container.querySelector('[data-sub-toolbar-rule]')!.hasAttribute('data-hidden')]).toEqual([false, false]);
});
