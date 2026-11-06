import React from 'react';
import { act, cleanup, fireEvent, render } from '@testing-library/react';
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
