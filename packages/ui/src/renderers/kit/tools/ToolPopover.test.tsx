import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import ToolPopover from '../../../../dist/renderers/kit/tools/ToolPopover.js';
import { ToolbarButton } from '../../../../dist/primitives/toolbar-button.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('a settings popover opens from its own button and closes on an outside press, Escape, or a second press', async () => {
  const user = userEvent.setup();
  const changes: boolean[] = [];
  render(<><button>Outside</button>
    <ToolPopover allowInactive label="Orbit options" onOpenChange={open => changes.push(open)}
      trigger={<ToolbarButton label="Orbit settings">o</ToolbarButton>}>Options</ToolPopover></>);
  const trigger = screen.getByRole('button', { name: 'Orbit settings' });
  await user.click(trigger);
  // Radix names a menu after its trigger; its own label is the attribute.
  expect(screen.getByRole('menu').getAttribute('aria-label')).toBe('Orbit options');
  await user.click(screen.getByRole('button', { name: 'Outside' }));
  expect(screen.queryByRole('menu')).toBeNull();
  await user.click(trigger);
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('menu')).toBeNull();
  await user.click(trigger);
  await user.click(trigger);
  expect(screen.queryByRole('menu')).toBeNull();
  // The owner hears it open and hears it close (fullscreen keeps its controls up meanwhile).
  expect([changes.includes(true), changes.at(-1)]).toEqual([true, false]);
});
