import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import FloatingToolBar from '../../../../dist/renderers/kit/tools/FloatingToolBar.js';
import { DropdownMenuCheckboxItem, DropdownMenuRadioGroup, DropdownMenuRadioItem } from '../../../../dist/primitives/dropdown-menu.js';

// A phone's strip (`FloatingToolBar`'s `touch`): the view's controls are rows of its More menu. A phone has no
// room beside More for a submenu (a board's More is wide enough that one opened on its left ran off the
// screen), so a control's choices open under its row, in More itself: one menu, laid out on screen as a menu is.

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

function Strip({ onMode = () => {}, onGrid = () => {} }) {
  const display = { id: 'display', label: 'Display', icon: null, tile: null,
    submenu: () => <>
      <DropdownMenuRadioGroup aria-label="Display mode" value="solid" onValueChange={onMode}>
        {['solid', 'shaded'].map(mode => <DropdownMenuRadioItem key={mode} value={mode}>{mode}</DropdownMenuRadioItem>)}
      </DropdownMenuRadioGroup>
      <DropdownMenuCheckboxItem checked={false} onCheckedChange={onGrid} onSelect={(event: Event) => event.preventDefault()}>Grid</DropdownMenuCheckboxItem>
    </> };
  const preview = { id: 'preview', label: 'Preview', icon: null, tile: null, onSelect() {} };
  return <FloatingToolBar touch tools={[{ id: 'select', label: 'Select', icon: null, onSelect() {} }]} views={[display, preview]} />;
}

it("on a phone, a control's choices open under its row in More itself, never in a menu of their own beside it", async () => {
  const user = userEvent.setup();
  const grid = vi.fn(), mode = vi.fn();
  render(<Strip onGrid={grid} onMode={mode} />);
  await user.click(screen.getByRole('button', { name: 'More tools' }));
  const more = screen.getByRole('menu', { name: 'More tools' });
  const row = screen.getByRole('menuitem', { name: 'Display' });
  expect([row.getAttribute('aria-expanded'), screen.queryByRole('group', { name: 'Display' })]).toEqual(['false', null]);
  await user.click(row);
  const choices = screen.getByRole('group', { name: 'Display' });
  // Under its row, in the same menu: no second menu to be placed beside More.
  expect([more.contains(choices), row.getAttribute('aria-expanded'), screen.getAllByRole('menu').length]).toEqual([true, 'true', 1]);
  expect(row.compareDocumentPosition(choices) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect([...choices.querySelectorAll('[role^=menuitem]')].map(item => item.textContent)).toEqual(['solid', 'shaded', 'Grid']);
  // Ticking Grid leaves More and the choices open; a press on the row hides them again, and Left and Right do the same.
  await user.click(screen.getByRole('menuitemcheckbox', { name: 'Grid' }));
  expect([grid.mock.calls, Boolean(screen.queryByRole('group', { name: 'Display' }))]).toEqual([[[true]], true]);
  await user.click(row);
  expect(screen.queryByRole('group', { name: 'Display' })).toBeNull();
  fireEvent.keyDown(row, { key: 'ArrowRight' });
  expect(row.getAttribute('aria-expanded')).toBe('true');
  fireEvent.keyDown(row, { key: 'ArrowLeft' });
  expect(row.getAttribute('aria-expanded')).toBe('false');
  // A mode chosen closes More; opened again, its choices start hidden.
  await user.click(row);
  await user.click(screen.getByRole('menuitemradio', { name: 'shaded' }));
  expect([mode.mock.calls, screen.queryByRole('menu', { name: 'More tools' })]).toEqual([[['shaded']], null]);
  await user.click(screen.getByRole('button', { name: 'More tools' }));
  expect(screen.getByRole('menuitem', { name: 'Display' }).getAttribute('aria-expanded')).toBe('false');
});
