import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import DisplaySettingsPopover from '../../../../dist/renderers/kit/view-settings/DisplaySettingsPopover.js';
import { TooltipProvider } from '../../../../dist/primitives/tooltip.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('Orbit expands and collapses and only shows orbit controls while active', async () => {
  const user = userEvent.setup();
  function Harness() {
    const [preview, change] = React.useState(false);
    return <TooltipProvider><button>Outside</button><DisplaySettingsPopover settings={null} preview={preview} onPreviewChange={change} /></TooltipProvider>;
  }
  render(<Harness />);
  await user.click(screen.getByRole('button', { name: 'Display', exact: true }));
  expect(screen.queryByRole('slider', { name: 'Orbit speed' })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Enable Orbit', exact: true }));
  expect(screen.getByRole('slider', { name: 'Orbit speed' })).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: 'Disable Orbit', exact: true }));
  expect(screen.queryByRole('slider', { name: 'Orbit speed' })).toBeNull();
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('dialog')).toBeNull();
});
