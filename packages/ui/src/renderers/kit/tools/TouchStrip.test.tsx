import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import FloatingToolBar from '../../../../dist/renderers/kit/tools/FloatingToolBar.js';

// A phone's strip (`FloatingToolBar`'s `touch`): one row of 36px tiles, its tools and nothing else. Those that do not
// fit the column it is centred in go, from the end, into More (an ellipsis, last), each a row ticked while in hand.

// jsdom lays nothing out: the strip's column is as wide as a test says.
let room = 0;
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  Object.defineProperty(HTMLElement.prototype, 'clientWidth', { configurable: true,
    get(this: HTMLElement) { return this.hasAttribute('data-cad-tool-groups') ? room : 0; } });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); delete (HTMLElement.prototype as { clientWidth?: number }).clientWidth; });

const TOOLS = ['Select', 'Draw', 'Measure', 'Explode', 'Clip'];
function strip(width: number, active: string) {
  room = width;
  const tools = TOOLS.map(label => ({ id: label, label, icon: null, active: label === active, onSelect: vi.fn() }));
  render(<div data-cad-tool-groups=""><FloatingToolBar touch tools={tools} /></div>);
  const tiles = within(screen.getByRole('group', { name: 'Interaction tools' })).getAllByRole('button').map(button => button.getAttribute('aria-label'));
  return { tools, tiles };
}

it("a phone's strip holds its tools alone, and what does not fit goes from its end into More, a row ticked while it is in hand", async () => {
  const user = userEvent.setup();
  // 200px: Select, Draw and Measure, then More with the two that do not fit; Clip, in hand there, lights More.
  const { tools, tiles } = strip(200, 'Clip');
  expect(tiles).toEqual(['Select', 'Draw', 'Measure', 'More tools']);
  const more = screen.getByRole('button', { name: 'More tools' });
  expect(more.getAttribute('data-variant')).toBe('secondary');
  await user.click(more);
  const menu = screen.getByRole('menu', { name: 'More tools' });
  // Its rows are those tools and nothing else: no Display, Preview or zoom.
  expect(within(menu).getAllByRole('menuitemcheckbox').map(row => [row.textContent, row.getAttribute('aria-checked')]))
    .toEqual([['Explode', 'false'], ['Clip', 'true']]);
  expect(menu.querySelectorAll('[role=menuitem]')).toHaveLength(0);
  await user.click(within(menu).getByRole('menuitemcheckbox', { name: 'Explode' }));
  expect(tools.map(tool => tool.onSelect.mock.calls.length)).toEqual([0, 0, 0, 1, 0]);
  cleanup();
  // With room for every tool there is no More.
  expect(strip(400, 'Select').tiles).toEqual(TOOLS);
  expect(screen.queryByRole('button', { name: 'More tools' })).toBeNull();
});
