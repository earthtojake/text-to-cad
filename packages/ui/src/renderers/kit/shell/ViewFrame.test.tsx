import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import ViewFrame from '../../../../dist/renderers/kit/shell/ViewFrame.js';
import { HOVER_TIP_DELAY_MS } from '../../../../dist/renderers/kit/shell/HoverTip.js';

globalThis.ResizeObserver ??= class { observe() {} unobserve() {} disconnect() {} } as any;
afterEach(cleanup);

// The update status is the frame's, one rule in every view, 2D or 3D (`settings-ui.md`): under the strip,
// at the top centre where there is no strip (a load, a compact host, Preview), and none while the card
// says why the chrome is gone; its Retry wherever the update offers one.
it('the update status stands under the strip, at the top centre without one, and gives way to the card of a view whose chrome is gone', () => {
  const failing = { pending: false, error: 'the GPU went away' };
  const status = { update: failing, onRetry: () => {} };
  const frame = (props: object) => render(<ViewFrame file="part.step" mobile={false} compact={false} chromeHidden={false} tools={[]} layout={{}}
    onLayoutChange={() => {}} status={status} {...props}>{null}</ViewFrame>);
  const where = (view: ReturnType<typeof render>) => {
    const node = view.container.querySelector('[data-viewport-status]');
    if (!node) return 'none';
    return [node.closest('[data-cad-top-controls]') ? 'under the strip' : 'top centre', Boolean(node.querySelector('button[aria-label="Retry view update"]'))];
  };
  expect(where(frame({}))).toEqual(['under the strip', true]);
  cleanup();
  expect(where(frame({ compact: true }))).toEqual(['top centre', true]);
  cleanup();
  expect(where(frame({ chromeHidden: true }))).toEqual(['top centre', true]);
  cleanup();
  expect(where(frame({ chromeHidden: true, alert: { alert: { severity: 'error', title: 'Could not open', message: 'no' }, hasContent: false } }))).toBe('none');
  cleanup();
  // A view with nothing to say draws no status, wherever it would stand.
  const idle = render(<ViewFrame file="part.step" mobile={false} compact chromeHidden={false} tools={[]} layout={{}} onLayoutChange={() => {}}
    status={{ update: null }}>{null}</ViewFrame>);
  expect(idle.container.querySelector('[data-view-update-status]')).toBeNull();
});

// What is picked is the frame's in every view (`settings-ui.md`): the Selected pane under the panel's
// lists and the hover tip over the canvas, both from the view's description of a pick (`inspect`).
it('the frame names what a press would pick in a tip beside the pointer, under Select and while no button is held, and shows the pick in the Selected pane', () => {
  vi.useFakeTimers();
  const item = { id: 'selected:#U3', pick: '#U3', kind: 'solid', title: 'U3', tip: 'ATmega328P', facts: [{ label: 'Value', value: 'ATmega328P' }] };
  const inspect = { selected: ['#U3'], describe: () => item, hovered: '#U3', select: () => {}, hover: () => {} };
  const panel = { kind: 'test', label: 'Panel', searchLabel: 'Search', tabs: [{ id: 'list', label: 'List', content: <p>rows</p> }] };
  const frame = (props: object) => render(<ViewFrame file="board.kicad_pcb" mobile={false} compact={false} chromeHidden={false} tools={[]} layout={{}}
    onLayoutChange={() => {}} selecting panel={panel} inspect={inspect} {...props}><canvas data-testid="canvas" /></ViewFrame>);
  const view = frame({});
  expect(view.container.querySelector('[data-flat-panel-detail] [data-detail-head]')!.textContent).toBe('U3');
  const canvas = view.getByTestId('canvas');
  fireEvent.pointerMove(canvas, { clientX: 40, clientY: 60, buttons: 0 });
  act(() => { vi.advanceTimersByTime(HOVER_TIP_DELAY_MS); });
  expect(view.getByRole('tooltip').textContent).toBe('U3 · ATmega328P');
  // A drag puts it away; another tool than Select shows none.
  fireEvent.pointerMove(canvas, { clientX: 50, clientY: 60, buttons: 1 });
  expect(view.queryByRole('tooltip')).toBeNull();
  cleanup();
  const other = frame({ selecting: false });
  fireEvent.pointerMove(other.getByTestId('canvas'), { clientX: 40, clientY: 60, buttons: 0 });
  act(() => { vi.advanceTimersByTime(HOVER_TIP_DELAY_MS); });
  expect(other.queryByRole('tooltip')).toBeNull();
  vi.useRealTimers();
});

it("the hover tip takes the view's short words where it has them, and never runs the full description for a hover", () => {
  vi.useFakeTimers();
  const describe = vi.fn(() => null);
  const inspect = { selected: [], describe, tip: (id: string) => `${id} · hinge`, hovered: 'pin', select: () => {}, hover: () => {} };
  const view = render(<ViewFrame file="part.step" mobile={false} compact={false} chromeHidden={false} tools={[]} layout={{}} onLayoutChange={() => {}}
    selecting inspect={inspect}><canvas data-testid="canvas" /></ViewFrame>);
  fireEvent.pointerMove(view.getByTestId('canvas'), { clientX: 10, clientY: 10, buttons: 0 });
  act(() => { vi.advanceTimersByTime(HOVER_TIP_DELAY_MS); });
  expect(view.getByRole('tooltip').textContent).toBe('pin · hinge');
  expect(describe).not.toHaveBeenCalled();
  vi.useRealTimers();
});

// Several picks: the pane draws one at a time, the active one, the last picked (Blender's active object), under a
// switcher of them all (`ItemDetail.jsx`'s `SelectedPane`): ‹ and › step and wrap, the count is a menu of every
// pick, ←/→ and [ ] step while it has the keyboard, the view lights the active pick while the pane is in use, and
// as the picks change it follows them: letting go of the active one hands it to the nearest left.
it('several picks: the pane draws the active one under a switcher that steps, wraps, lists them all and follows the picks', async () => {
  const user = userEvent.setup({ skipHover: true });
  const item = (name: string) => ({ id: `selected:#${name}`, pick: `#${name}`, kind: 'solid', title: name, tip: `${name} tip`, facts: [] });
  const hover = vi.fn();
  const panel = { kind: 'test', label: 'Panel', searchLabel: 'Search', tabs: [{ id: 'list', label: 'List', content: <p>rows</p> }] };
  const frame = (selected: string[]) => <ViewFrame file="board.kicad_pcb" mobile={false} compact={false} chromeHidden={false} tools={[]} layout={{}}
    onLayoutChange={() => {}} panel={panel} inspect={{ selected, describe: (id: string) => item(id.slice(1)), select: () => {}, hover }}><canvas /></ViewFrame>;
  const view = render(frame(['#U1']));
  const head = () => view.container.querySelector('[data-flat-panel-detail] [data-detail-head]')!.textContent;
  const count = () => view.container.querySelector('[data-flat-panel-picks-count]')?.textContent ?? null;
  // One pick: its detail, and no switcher.
  expect([head(), count()]).toEqual(['U1', null]);
  // Two more, added: the last is the active one.
  view.rerender(frame(['#U1', '#C1', '#R1']));
  expect([head(), count()]).toEqual(['R1', '3 of 3']);
  const group = screen.getByRole('group', { name: 'Picks' });
  expect([...group.querySelectorAll('button')].map(button => button.getAttribute('aria-label'))).toEqual(['Previous pick', 'Pick 3 of 3', 'Next pick']);
  // › wraps to the first, ‹ back to the last.
  await user.click(screen.getByRole('button', { name: 'Next pick' }));
  expect([head(), count()]).toEqual(['U1', '1 of 3']);
  await user.click(screen.getByRole('button', { name: 'Previous pick' }));
  expect([head(), count()]).toEqual(['R1', '3 of 3']);
  // With the keyboard on the switcher, ← and ] step; the view lights the active pick meanwhile.
  fireEvent.keyDown(screen.getByRole('button', { name: 'Previous pick' }), { key: 'ArrowLeft' });
  expect([head(), count()]).toEqual(['C1', '2 of 3']);
  expect(hover).toHaveBeenLastCalledWith('#C1');
  fireEvent.keyDown(screen.getByRole('button', { name: 'Previous pick' }), { key: ']' });
  expect([head(), count()]).toEqual(['R1', '3 of 3']);
  // The count is a menu of every pick, its name and short kind, the active one ticked; a choice makes it active.
  await user.click(screen.getByRole('button', { name: 'Pick 3 of 3' }));
  const menu = await waitFor(() => { const found = document.querySelector<HTMLElement>('[role=menu][aria-label="Picks"]'); expect(found).not.toBeNull(); return found!; });
  expect([...menu.querySelectorAll('[role=menuitemradio]')].map(row => [row.textContent, row.getAttribute('aria-checked')]))
    .toEqual([['U1U1 tip', 'false'], ['C1C1 tip', 'false'], ['R1R1 tip', 'true']]);
  await user.click(screen.getByRole('menuitemradio', { name: /^U1/ }));
  await waitFor(() => expect(document.querySelector('[role=menu][aria-label="Picks"]')).toBeNull());
  expect([head(), count()]).toEqual(['U1', '1 of 3']);
  // The active one let go of (Shift on it): the nearest left, the one after it, takes over.
  view.rerender(frame(['#C1', '#R1']));
  expect([head(), count()]).toEqual(['C1', '1 of 2']);
  // One left: its detail, and no switcher.
  view.rerender(frame(['#R1']));
  expect([head(), count()]).toEqual(['R1', null]);
});
