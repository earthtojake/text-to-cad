import React, { useState, useSyncExternalStore } from 'react';
import { createViewSettingsStore } from '../../../../../dist/renderers/kit/view-settings/viewSettingsStore.js';
import { resolveViewSettings } from '@cad/core/common/viewSettings.js';
import { act, cleanup, fireEvent, render, renderHook, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { useModelTools } from '../../../../../dist/renderers/kit/tools/model-effects/ModelTools.js';
import FloatingToolBar from '../../../../../dist/renderers/kit/tools/FloatingToolBar.js';
import { SUB_TOOLBAR_WIDTH_CLASS } from '../../../../../dist/renderers/kit/tools/SubToolbar.js';
import { ControlUsageProvider } from '../../../../../dist/usage/controls.js';

beforeEach(() => { vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }); });
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
const neutral = () => resolveViewSettings({});

// The strip as FloatingToolBar draws it, Select beside the effects, the effect in hand's row under it, as the shell
// keeps it (`useRendererShell`'s `effectTool`: Select the mode underneath), and the model.
function Strip({ store, settings = ['exploded', 'clip'] }: { store: ReturnType<typeof createViewSettingsStore>; settings?: string[] }) {
  const snapshot = useSyncExternalStore(store.subscribe, store.getSnapshot);
  const [inHand, setInHand] = useState<string | null>(null);
  const tools = useModelTools({ view: snapshot.scene.view, features: { settings }, store,
    mesh: { bounds: { min: [0, 0, 0], max: [10, 10, 10] } }, disabled: false, shell: { effectTool: inHand, selectEffectTool: setInHand } });
  const select = { id: 'select', label: 'Select', icon: <span>S</span>, active: inHand === null, onSelect: () => setInHand(null) };
  return <><div data-testid="model">model</div><FloatingToolBar tools={[select, ...tools.tools]} />{tools.subToolbar}</>;
}
const pressed = (button: HTMLElement) => button.getAttribute('aria-pressed');

it('Explode and Clip are tools of the strip: a press takes one up, pressed, its row under the strip, the drawing tools\' width', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0, skipHover: true });
  const store = createViewSettingsStore();
  render(<Strip store={store} />);
  const explode = screen.getByRole('button', { name: 'Explode', exact: true });
  const row = () => screen.queryByRole('toolbar', { name: 'Explode controls' });
  expect([row(), pressed(explode)]).toEqual([null, 'false']);
  await user.click(explode);
  // Its row: its name, the slider, the amount, Reset; no popover; the button pressed, Select not.
  expect([...row()!.querySelectorAll('[data-slider-field-value], button[aria-label], [role=slider]')].map(node => (node as HTMLInputElement).value || node.getAttribute('aria-label')))
    .toEqual(['Explode amount', '0', 'Reset explode']);
  expect([row()!.closest('[data-radix-popper-content-wrapper]'), pressed(explode), pressed(screen.getByRole('button', { name: 'Select' }))]).toEqual([null, 'true', 'false']);
  // One width with the drawing tools' row (`SUB_TOOLBAR_WIDTH_CLASS`).
  expect(row()!.className.split(' ')).toContain(SUB_TOOLBAR_WIDTH_CLASS);
  // A press on the model leaves it in hand; Clip taken up puts Explode down, one row at a time.
  await user.click(screen.getByTestId('model'));
  expect(row()).not.toBeNull();
  await user.click(screen.getByRole('button', { name: 'Clip', exact: true }));
  expect([row(), screen.getByRole('toolbar', { name: 'Clip controls' }).className.split(' ').includes(SUB_TOOLBAR_WIDTH_CLASS), pressed(explode)]).toEqual([null, true, 'false']);
});

it('what an effect sets stays on the model once another tool is taken up, its dot on the tile, until its Reset', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0, skipHover: true });
  const store = createViewSettingsStore();
  render(<Strip store={store} />);
  const explode = () => screen.getByRole('button', { name: 'Explode', exact: true });
  await user.click(explode());
  fireEvent.keyDown(screen.getByRole('slider', { name: 'Explode amount' }), { key: 'PageUp' });
  const amount = store.getSnapshot().scene.view.exploded.amount;
  expect([store.getSnapshot().scene.view.exploded.enabled, amount > 0, explode().hasAttribute('data-changed')]).toEqual([true, true, false]);
  await user.click(screen.getByRole('button', { name: 'Select' }));
  expect(screen.queryByRole('toolbar', { name: 'Explode controls' })).toBeNull();
  // Put down: still exploded, the tile's dot saying so, the button not pressed.
  expect([store.getSnapshot().scene.view.exploded.amount, explode().hasAttribute('data-changed'), pressed(explode())]).toEqual([amount, true, 'false']);
  // Taken up again, as it was; Reset takes it away, and the row stays up.
  await user.click(explode());
  expect(screen.getByRole('toolbar', { name: 'Explode controls' }).querySelector<HTMLInputElement>('[data-slider-field-value]')!.value).toBe(`${Math.round(amount * 100)}`);
  await user.click(screen.getByRole('button', { name: 'Reset explode' }));
  expect([store.getSnapshot().scene.view.exploded.enabled, explode().hasAttribute('data-changed'), screen.queryByRole('toolbar', { name: 'Explode controls' }) !== null]).toEqual([false, false, true]);
});

it('each time an effect is taken up is one use of it, under its old name, and its Reset one of its reset', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0, skipHover: true });
  const store = createViewSettingsStore();
  const reports: { control: string; count: number; seconds: number }[][] = [];
  const view = render(<ControlUsageProvider report={counts => reports.push(counts)}><Strip store={store} /></ControlUsageProvider>);
  await user.click(screen.getByRole('button', { name: 'Explode', exact: true }));
  fireEvent.keyDown(screen.getByRole('slider', { name: 'Explode amount' }), { key: 'PageUp' });
  await user.click(screen.getByRole('button', { name: 'Reset explode' }));
  // A press on the tool in hand is no second use.
  await user.click(screen.getByRole('button', { name: 'Explode', exact: true }));
  await user.click(screen.getByRole('button', { name: 'Select' }));
  await user.click(screen.getByRole('button', { name: 'Explode', exact: true }));
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

it('Clip\'s axis dropdown holds its settings: the axes as one row of radio items, a rule, then Part colours and Reverse; all kept as it is put down and by Reset, which only takes the cut away; both persist in the display', async () => {
  const user = userEvent.setup({ pointerEventsCheck: 0, skipHover: true });
  const store = createViewSettingsStore();
  render(<Strip store={store} settings={['clip']} />);
  const clip = () => store.getSnapshot().scene.view.clip;
  const takeUp = (name: string) => user.click(screen.getByRole('button', { name, exact: true }));
  // Putting Clip down: Select taken up.
  const putDown = () => user.click(screen.getByRole('button', { name: 'Select' }));
  const axisButton = () => screen.getByRole('toolbar', { name: 'Clip controls' }).querySelector<HTMLElement>('[data-clip-axis]')!;
  // The menu is named by its trigger, as every dropdown here is.
  const menu = () => screen.getByRole('menu', { name: /^Clip axis: [XYZ]$/ });
  const item = (name: string) => screen.getByRole('menuitemcheckbox', { name });
  const ticks = () => ['Part colours', 'Reverse'].map(name => item(name).getAttribute('aria-checked'));
  // What the menu holds, top to bottom: the three axes (one group), then the two settings — no heading.
  const reads = () => [...menu().querySelectorAll('[role=menuitemradio], [role=menuitemcheckbox], [data-slot=dropdown-menu-label]')]
    .map(node => `${node.getAttribute('role')}:${node.getAttribute('aria-label') || node.textContent}:${node.getAttribute('aria-checked')}`);
  const share = () => screen.getByRole('toolbar', { name: 'Clip controls' }).querySelector<HTMLInputElement>('[data-slider-field-value]')!.value;
  await takeUp('Clip');
  // The row: axis, slider, amount, Reset — Explode's shape, no checkbox and no other button.
  const row = screen.getByRole('toolbar', { name: 'Clip controls' });
  expect([...row.querySelectorAll('[data-slider-field-value], button[aria-label]')].map(node => (node as HTMLInputElement).value || node.getAttribute('aria-label')))
    .toEqual(['Clip axis: X', '0', 'Reset clip']);
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
  // Escape closed the menu alone: Clip's row is still up, as every choice in it kept it.
  expect([screen.queryByRole('menu'), screen.queryByRole('toolbar', { name: 'Clip controls' }) !== null]).toEqual([null, true]);
  // A cut: Reverse turns it round keeping its share.
  fireEvent.keyDown(screen.getByRole('slider', { name: 'Clip amount' }), { key: 'PageUp' });
  const cut = share();
  expect([clip().enabled, cut]).toEqual([true, expect.stringMatching(/^[1-9]\d*$/)]);
  await user.click(axisButton());
  await user.click(item('Reverse'));
  expect([clip().invert, share(), clip().enabled]).toEqual([false, cut, true]);
  await user.click(item('Reverse'));
  await user.keyboard('{Escape}');
  // Put down and taken up again, all as it was.
  await putDown();
  expect(screen.queryByRole('toolbar', { name: 'Clip controls' })).toBeNull();
  await takeUp('Clip');
  expect([clip().enabled, clip().axis, clip().partColors, clip().invert, share()]).toEqual([true, 'y', false, true, cut]);
  // Reset: the amount back at zero, nothing else; an unset Clip taken up again changes nothing either.
  await user.click(screen.getByRole('button', { name: 'Reset clip' }));
  expect([clip().enabled, clip().axis, clip().partColors, clip().invert, share()]).toEqual([false, 'y', false, true, '0']);
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
