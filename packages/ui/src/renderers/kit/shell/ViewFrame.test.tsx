import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import ViewFrame from '../../../../dist/renderers/kit/shell/ViewFrame.js';

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
