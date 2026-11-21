import React from 'react';
import { cleanup, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import DisplayPopover from '../../../../dist/renderers/kit/shell/DisplayPopover.js';
import { DISPLAY_MODE_OPTIONS } from '../../../../dist/renderers/kit/view-settings/DisplayModeOptions.js';

Object.assign(globalThis, { React });
beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

// The Display tile of an assembly with parts baked from a concept: its modes, the Grid switch, then how those
// parts are shown, as the assembly's view hands it (`XbfRenderer.jsx`).
function Harness({ shownAs }: { shownAs?: { value: string, onChange(value: string): void } | null }) {
  return <DisplayPopover mode={{ value: 'solid', options: DISPLAY_MODE_OPTIONS, onChange: () => {} }}
    grid={{ value: false, onChange: () => {} }} shownAs={shownAs} />;
}
const open = async () => {
  await userEvent.setup({ skipHover: true }).click(screen.getByRole('button', { name: /^Display mode:/ }));
  return document.querySelector<HTMLElement>('[role=menu][aria-label="Display"]')!;
};

it('ends with Show as, Exact and Concept, where the model has parts baked from a concept', async () => {
  const onChange = vi.fn();
  render(<Harness shownAs={{ value: 'exact', onChange }} />);
  const group = within(await open()).getByRole('group', { name: 'Show as' });
  const ways = within(group).getAllByRole('menuitemradio');
  expect(ways.map(item => [item.textContent, item.getAttribute('aria-checked')])).toEqual([['Exact', 'true'], ['Concept', 'false']]);
  // The one on screen chosen again changes nothing; the other is asked for by its name.
  await userEvent.setup({ skipHover: true }).click(ways[1]);
  expect(onChange.mock.calls).toEqual([['concept']]);
});

it('ticks neither while the baked parts differ', async () => {
  render(<Harness shownAs={{ value: '', onChange: () => {} }} />);
  const group = within(await open()).getByRole('group', { name: 'Show as' });
  expect(within(group).getAllByRole('menuitemradio').map(item => item.getAttribute('aria-checked'))).toEqual(['false', 'false']);
});

it('is not in the list of a model with no baked part', async () => {
  render(<Harness shownAs={null} />);
  expect(within(await open()).queryByRole('group', { name: 'Show as' })).toBeNull();
});
