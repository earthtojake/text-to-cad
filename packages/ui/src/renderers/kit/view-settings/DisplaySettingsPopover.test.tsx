import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import DisplaySettingsPopover from '../../../../dist/renderers/kit/view-settings/DisplaySettingsPopover.js';
import { TooltipProvider } from '../../../../dist/primitives/tooltip.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('activates Display, releases the tool when its sheet closes, and closes when another tool is selected', async () => {
  const user = userEvent.setup();
  const activate = vi.fn();
  function Harness() {
    const [active, setActive] = React.useState(false);
    return <TooltipProvider><button onClick={() => setActive(false)}>Select</button>
      <DisplaySettingsPopover active={active} onActivate={() => { activate(); setActive(true); }} onDeactivate={() => setActive(false)} settings={<p>Display properties</p>} />
    </TooltipProvider>;
  }
  render(<Harness />);
  const display = screen.getByRole('button', { name: 'Display', exact: true });
  await user.click(display);
  expect(activate).toHaveBeenCalledOnce();
  expect(screen.getByRole('dialog', { name: 'Display settings' })).toBeTruthy();
  await user.click(display);
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(display.getAttribute('aria-pressed')).toBe('false');
  await user.click(display);
  await user.keyboard('{Escape}');
  expect(display.getAttribute('aria-pressed')).toBe('false');
  await user.click(display);
  await user.click(screen.getByRole('button', { name: 'Select', exact: true }));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(display.getAttribute('aria-pressed')).toBe('false');
});
