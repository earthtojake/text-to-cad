import React, { useState, useSyncExternalStore } from 'react';
import { createViewSettingsStore } from '../../../../../dist/renderers/kit/view-settings/viewSettingsStore.js';
import { resolveViewSettings } from '@text-to-cad/core/common/viewSettings.js';
import { act, cleanup, fireEvent, render, renderHook, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useModelTools } from '../../../../../dist/renderers/kit/tools/model-effects/ModelTools.js';
import { ControlUsageProvider } from '../../../../../dist/usage/controls.js';

beforeEach(() => { vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const neutral = () => resolveViewSettings({});

// The strip's tiles, as FloatingToolBar draws a tool with a `tile`, and a click-away target.
function Strip({ store, settings = ['exploded', 'clip'] }: { store: ReturnType<typeof createViewSettingsStore>; settings?: string[] }) {
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const tools = useModelTools({ view: snapshot.scene.view, features: { settings }, store,
    mesh: { bounds: { min: [0, 0, 0], max: [10, 10, 10] } }, disabled: false });
  return <><div data-testid="model">model</div>{tools.tools.map(tool => <React.Fragment key={tool.id}>{tool.tile}</React.Fragment>)}</>;
}

it('Explode and Clip are popovers from their tiles: a press opens the row under its button, a press away or Escape closes it, and the button is never pressed', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0, skipHover: true });
  const store = createViewSettingsStore();
  render(<Strip store={store} />);
  const explode = screen.getByRole('button', { name: 'Explode', exact: true });
  const row = () => screen.queryByRole('toolbar', { name: 'Explode controls' });
  const pressed = (button: HTMLElement) => [button.getAttribute('aria-pressed'), button.hasAttribute('data-active'), button.getAttribute('data-variant')];
  expect([row(), pressed(explode)]).toEqual([null, [null, false, 'ghost']]);
  await user.click(explode);
  // Its row as it was under the strip: its name, the slider, the amount, Reset; the button not pressed.
  expect([...row()!.querySelectorAll('[data-model-tool-amount], button[aria-label], [role=slider]')].map(node => node.getAttribute('aria-label') || node.textContent))
    .toEqual(['Explode amount', '0%', 'Reset explode']);
  expect(row()!.closest('[data-radix-popper-content-wrapper]')).not.toBeNull();
  expect(pressed(explode)).toEqual([null, false, 'ghost']);
  // A press away (on the model) closes it; so does Escape; so does its button again.
  await user.click(screen.getByTestId('model'));
  expect(row()).toBeNull();
  await user.click(explode);
  await user.keyboard('{Escape}');
  expect(row()).toBeNull();
  await user.click(explode);
  await user.click(explode);
  expect(row()).toBeNull();
  // Clip's is its own, one open at a time as any popover.
  await user.click(screen.getByRole('button', { name: 'Clip', exact: true }));
  expect([row(), screen.getByRole('toolbar', { name: 'Clip controls' }) !== null]).toEqual([null, true]);
});

it('what an effect sets stays on the model once its popover closes, its dot on the tile, until its Reset', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0, skipHover: true });
  const store = createViewSettingsStore();
  render(<Strip store={store} />);
  const explode = () => screen.getByRole('button', { name: 'Explode', exact: true });
  await user.click(explode());
  fireEvent.keyDown(screen.getByRole('slider', { name: 'Explode amount' }), { key: 'PageUp' });
  const amount = store.getSnapshot().scene.view.exploded.amount;
  expect([store.getSnapshot().scene.view.exploded.enabled, amount > 0]).toEqual([true, true]);
  await user.keyboard('{Escape}');
  expect(screen.queryByRole('toolbar', { name: 'Explode controls' })).toBeNull();
  // Closed: still exploded, the tile's dot saying so, the button still not pressed.
  expect([store.getSnapshot().scene.view.exploded.amount, explode().hasAttribute('data-changed'), explode().getAttribute('aria-pressed')]).toEqual([amount, true, null]);
  // Opened again, as it was; Reset takes it away, and the popover stays up.
  await user.click(explode());
  expect(screen.getByRole('toolbar', { name: 'Explode controls' }).querySelector('[data-model-tool-amount]')!.textContent).toBe(`${Math.round(amount * 100)}%`);
  await user.click(screen.getByRole('button', { name: 'Reset explode' }));
  expect([store.getSnapshot().scene.view.exploded.enabled, explode().hasAttribute('data-changed'), screen.queryByRole('toolbar', { name: 'Explode controls' }) !== null]).toEqual([false, false, true]);
});

it('each popover opened is one use of its effect, with no seconds (it is no tool in hand), and its Reset one of its reset', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0, skipHover: true });
  const store = createViewSettingsStore();
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}><Strip store={store} /></ControlUsageProvider>);
  await user.click(screen.getByRole('button', { name: 'Explode', exact: true }));
  fireEvent.keyDown(screen.getByRole('slider', { name: 'Explode amount' }), { key: 'PageUp' });
  await user.click(screen.getByRole('button', { name: 'Reset explode' }));
  await user.keyboard('{Escape}');
  await user.click(screen.getByRole('button', { name: 'Explode', exact: true }));
  await user.keyboard('{Escape}');
  await user.click(screen.getByRole('button', { name: 'Clip', exact: true }));
  view.unmount();
  const said = Object.fromEntries(reports.flat().map(({ control, ...counts }) => [control, counts]));
  expect([said.explode, said.clip, said.explode_reset]).toEqual([{ count: 2, seconds: 0 }, { count: 1, seconds: 0 }, { count: 1, seconds: 0 }]);
});

it('offers Explode and Clip on every STEP, a single part too, and idles them while the model loads', () => {
  const part = (id: string) => ({ id, bounds: { min: [0, 0, 0], max: [1, 1, 1] } });
  const props = { view: neutral(), features: { settings: ['exploded', 'clip'] }, store: { patch: vi.fn() },
    mesh: null as null | object, disabled: true };
  const { result, rerender } = renderHook(options => useModelTools(options), { initialProps: props });
  const offered = () => result.current.tools.map(tool => `${tool.id}:${tool.disabled}`);
  // Loading, idle; then every STEP has both, a single part too (its Explode separates nothing).
  expect(offered()).toEqual(['exploded:true', 'clip:true']);
  rerender({ ...props, disabled: false, mesh: { parts: [part('a')] } });
  expect(offered()).toEqual(['exploded:false', 'clip:false']);
  rerender({ ...props, disabled: false, mesh: { parts: [part('a'), part('b')] } });
  expect(offered()).toEqual(['exploded:false', 'clip:false']);
});

it('Clip\'s axis dropdown holds its settings: the axes as one row of radio items, a rule, then Part colours and Reverse; all kept as its popover closes and by Reset, which only takes the cut away; both persist in the display', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0, skipHover: true });
  const store = createViewSettingsStore();
  function Harness() {
    const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot);
    const tools = useModelTools({ view: snapshot.scene.view, features: { settings: ['clip'] }, store,
      mesh: { bounds: { min: [0, 0, 0], max: [10, 10, 10] } }, disabled: false });
    return <>{tools.tools.map(tool => <React.Fragment key={tool.id}>{tool.tile}</React.Fragment>)}</>;
  }
  render(<Harness />);
  const clip = () => store.getSnapshot().scene.view.clip;
  const takeUp = (name: string) => user.click(screen.getByRole('button', { name, exact: true }));
  // Closing Clip's popover: Escape, once its menu (if open) has closed.
  const putDown = () => user.keyboard('{Escape}');
  const axisButton = () => screen.getByRole('toolbar', { name: 'Clip controls' }).querySelector<HTMLElement>('[data-clip-axis]')!;
  // The menu is named by its trigger, as every dropdown here is.
  const menu = () => screen.getByRole('menu', { name: /^Clip axis: [XYZ]$/ });
  const item = (name: string) => screen.getByRole('menuitemcheckbox', { name });
  const ticks = () => ['Part colours', 'Reverse'].map(name => item(name).getAttribute('aria-checked'));
  // What the menu holds, top to bottom: the three axes (one group), then the two settings — no heading.
  const reads = () => [...menu().querySelectorAll('[role=menuitemradio], [role=menuitemcheckbox], [data-slot=dropdown-menu-label]')]
    .map(node => `${node.getAttribute('role')}:${node.getAttribute('aria-label') || node.textContent}:${node.getAttribute('aria-checked')}`);
  const share = () => screen.getByRole('toolbar', { name: 'Clip controls' }).querySelector('[data-model-tool-amount]')!.textContent;
  await takeUp('Clip');
  // The row: axis, slider, amount, Reset — Explode's shape, no checkbox and no other button.
  const row = screen.getByRole('toolbar', { name: 'Clip controls' });
  expect([...row.querySelectorAll('[data-model-tool-amount], button[aria-label]')].map(node => node.getAttribute('aria-label') || node.textContent))
    .toEqual(['Clip axis: X', '0%', 'Reset clip']);
  expect(within(row).queryByRole('checkbox')).toBeNull();
  // By keyboard: Enter opens it on the axis in hand; Space on a setting ticks it and leaves it open.
  axisButton().focus();
  await user.keyboard('{Enter}');
  expect(reads()).toEqual(['menuitemradio:X:true', 'menuitemradio:Y:false', 'menuitemradio:Z:false',
    'menuitemcheckbox:Part colours:true', 'menuitemcheckbox:Reverse:false']);
  expect(within(menu()).getByRole('group', { name: 'Clip axis' })).toBeTruthy();
  expect(document.activeElement?.textContent).toBe('X');
  await user.keyboard('{ArrowDown}{ArrowDown}{ArrowDown}');
  expect(document.activeElement).toBe(item('Part colours'));
  await user.keyboard(' ');
  await user.click(item('Reverse'));
  // An axis chosen keeps the menu open, the button reads it; none of them applies a cut.
  await user.click(screen.getByRole('menuitemradio', { name: 'Y' }));
  expect([reads(), axisButton().textContent, clip().enabled, clip().axis, clip().partColors, clip().invert]).toEqual([
    ['menuitemradio:X:false', 'menuitemradio:Y:true', 'menuitemradio:Z:false', 'menuitemcheckbox:Part colours:false', 'menuitemcheckbox:Reverse:true'],
    'Y', false, 'y', false, true]);
  await user.keyboard('{Escape}');
  // Escape closed the menu alone: the popover it opened in is still up, as every choice in it kept it.
  expect([screen.queryByRole('menu'), screen.queryByRole('toolbar', { name: 'Clip controls' }) !== null]).toEqual([null, true]);
  // A cut: Reverse turns it round keeping its share.
  fireEvent.keyDown(screen.getByRole('slider', { name: 'Clip amount' }), { key: 'PageUp' });
  const cut = share();
  expect([clip().enabled, cut]).toEqual([true, expect.stringMatching(/^[1-9]\d*%$/)]);
  await user.click(axisButton());
  await user.click(item('Reverse'));
  expect([clip().invert, share(), clip().enabled]).toEqual([false, cut, true]);
  await user.click(item('Reverse'));
  await user.keyboard('{Escape}');
  // Closed and opened again, all as it was.
  await putDown();
  expect(screen.queryByRole('toolbar', { name: 'Clip controls' })).toBeNull();
  await takeUp('Clip');
  expect([clip().enabled, clip().axis, clip().partColors, clip().invert, share()]).toEqual([true, 'y', false, true, cut]);
  // Reset: the amount back at zero, nothing else; an unset Clip taken up again changes nothing either.
  await user.click(screen.getByRole('button', { name: 'Reset clip' }));
  expect([clip().enabled, clip().axis, clip().partColors, clip().invert, share()]).toEqual([false, 'y', false, true, '0%']);
  await putDown();
  await takeUp('Clip');
  expect([clip().axis, clip().partColors, clip().invert]).toEqual(['y', false, true]);
  await user.click(axisButton());
  expect(ticks()).toEqual(['false', 'true']);
  // Both persist in the display as stored, and a restored display reads them back; validation stays strict.
  const stored = store.getSnapshot().display.clip;
  expect([stored.partColors, stored.invert]).toEqual([false, true]);
  expect(createViewSettingsStore(store.getSnapshot().display).getSnapshot().scene.view.clip).toMatchObject({ axis: 'y', partColors: false, invert: true });
  expect(() => createViewSettingsStore({ clip: { reverse: true } })).toThrow();
  expect(() => createViewSettingsStore({ clip: { partColors: 'false' } })).toThrow();
  expect(createViewSettingsStore().getSnapshot().scene.view.clip).toMatchObject({ partColors: true, invert: false });
});
