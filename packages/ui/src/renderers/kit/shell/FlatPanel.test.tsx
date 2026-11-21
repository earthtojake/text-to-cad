import { useState } from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import FlatPanel, { FlatPanelChanged, fitTabs, useFlatPanel, useFlatPanelMatches } from './FlatPanel.jsx';

afterEach(() => { cleanup(); vi.restoreAllMocks(); });

// A tab's list as a tree-like tab draws one: what the panel's query finds in it (all of it while nothing is typed),
// its count told to the panel.
function Hits({ items }: { items: string[] }) {
  const panel = useFlatPanel();
  const query = panel?.query.trim().toLowerCase() ?? '';
  const found = query ? items.filter(item => item.toLowerCase().includes(query)) : items;
  useFlatPanelMatches(query ? found.length : null);
  return <ul data-query={query}>{found.map(item => <li key={item}>{item}</li>)}</ul>;
}
// The panel with its tab held as a view holds it.
function Panel({ tabs, first, focusSearch = 0, onTab = () => {} }: { tabs: any[], first: string, focusSearch?: number, onTab?: (id: string) => void }) {
  const [tab, setTab] = useState(first);
  return <FlatPanel mode="docked" open onClose={() => {}} label="Panel" searchLabel="Search the board" tabs={tabs} tab={tab}
    onTabChange={(id: string) => { onTab(id); setTab(id); }} width={240} maxWidth={400} onWidthChange={() => {}} focusSearch={focusSearch} />;
}
const row = () => document.querySelector<HTMLElement>('[data-flat-panel-head]')!;
const searchIcon = () => screen.queryByRole('button', { name: 'Search the board' });
const box = () => screen.queryByRole('textbox', { name: 'Search the board' }) as HTMLInputElement | null;
const tabNames = () => screen.getAllByRole('tab').map(tab => tab.textContent!.replace(/^(\D+?)\1/, '$1'));

// The tabs are pills, as Figma's right panel draws them: the open one on the accent's subtle fill, its name the
// foreground's at medium weight, the others muted on no fill; the head one row, its rule under it: the tabs at its
// left, the search's icon at its right end, and no ⋯ where every tab fits.
it('draws its tabs as pills, the open one filled, foreground and medium, the others muted, the search an icon at the row\'s right end', () => {
  render(<Panel tabs={[{ id: 'parts', label: 'Parts', content: <p>Parts</p> }, { id: 'nets', label: 'Nets', content: <p>Nets</p> }]} first="nets" />);
  const tabs = screen.getAllByRole('tab');
  expect(tabs.map(tab => [tab.getAttribute('aria-selected'), tab.classList.contains('bg-accent'), tab.classList.contains('text-foreground'),
    tab.classList.contains('text-muted-foreground'), Boolean(tab.querySelector('[data-flat-panel-tab-name].font-medium')), tab.classList.contains('h-7'), tab.classList.contains('px-[5px]')]))
    .toEqual([['false', false, false, true, false, true, true], ['true', true, true, false, true, true, true]]);
  expect(row().style.padding).toBe('8px');
  expect([row().classList.contains('border-border'), row().hasAttribute('data-rule')]).toEqual([true, true]);
  // The row: the tab row (its tablist taking the room), then the search's icon, last; no ⋯, no search box.
  const line = row().firstElementChild as HTMLElement;
  expect([...line.children].map(child => child.getAttribute('data-flat-panel-tab-row') !== null ? 'tabs' : child.getAttribute('aria-label'))).toEqual(['tabs', 'Search the board']);
  expect([document.querySelector('[data-flat-panel-more]'), box(), document.querySelector('[data-flat-panel-body] [data-flat-panel-search]')]).toEqual([null, null, null]);
  expect(screen.getByRole('tablist').classList.contains('flex-1')).toBe(true);
  expect(document.querySelector('aside[data-flat-panel]')!.getAttribute('style')).toMatch(/width: 240px/);
});

// One tab is a plain title in the tab's place: no pill, no fill, a list row's height (28px), 8px over it and nothing
// under it, its list 4px under it; the search's icon at the row's right end, as with several.
it('draws a single tab as a plain title a row high, its list right under it, the search an icon at the right, and several as pills over the rule', () => {
  render(<Panel tabs={[{ id: 'model', label: 'Model', content: <p>tree</p> }]} first="model" />);
  const title = row().querySelector<HTMLElement>('[data-flat-panel-heading]')!;
  expect([screen.queryAllByRole('tab').length, screen.queryByRole('tablist'), title.textContent]).toEqual([0, null, 'Model']);
  expect([title.classList.contains('font-medium'), title.classList.contains('px-2'), title.classList.contains('h-7')]).toEqual([true, true, true]);
  expect([row().classList.contains('border-transparent'), row().hasAttribute('data-compact'), row().classList.contains('h-7'), row().style.padding]).toEqual([true, true, true, '8px 8px 0px']);
  expect([...row().children].map(child => child.getAttribute('aria-label') ?? child.tagName.toLowerCase())).toEqual(['h2', 'Search the board']);
  expect(document.querySelector('[data-flat-panel-body]')!.classList.contains('pt-1')).toBe(true);
  expect(document.querySelector('[data-flat-panel-section="model"]')!.getAttribute('aria-labelledby')).toBe(title.id);
  cleanup();
  render(<Panel tabs={[{ id: 'parts', label: 'Parts', content: <p>Parts</p> }, { id: 'nets', label: 'Nets', content: <p>Nets</p> }]} first="parts" />);
  expect([screen.getAllByRole('tab').length, document.querySelector('[data-flat-panel-heading]'), row().hasAttribute('data-compact'), row().classList.contains('h-8')]).toEqual([2, null, false, true]);
});

// "/" puts the keyboard in the search once per press: the panel closed and opened again, or mounted
// again, leaves the focus where it is, so the next V, M or P is a tool's key and not typed in the search.
it('focuses its search once for each press of /, never again when it reopens or remounts', () => {
  const panel = (open: boolean, focusSearch: number, key = 'a') => <FlatPanel key={key} mode="docked" open={open} onClose={() => {}} label="Panel" searchLabel="Search"
    tabs={[{ id: 'parts', label: 'Parts', content: <p>Parts</p> }]} tab="parts" onTabChange={() => {}} width={216} maxWidth={400}
    onWidthChange={() => {}} focusSearch={focusSearch} />;
  const { rerender } = render(panel(true, 0));
  const search = () => document.querySelector('[data-flat-panel-search] input');
  rerender(panel(true, 1));
  expect(document.activeElement).toBe(search());
  act(() => { (document.activeElement as HTMLElement).blur(); });
  rerender(panel(false, 1));
  rerender(panel(true, 1));
  expect(document.activeElement).toBe(document.body);
  rerender(panel(true, 1, 'b'));
  expect(document.activeElement).toBe(document.body);
  rerender(panel(true, 2, 'b'));
  expect(document.activeElement).toBe(search());
});

// The search's icon opens the search: the row is its box, the X where the icon was, the tabs under it. A query
// filters every searchable tab at once, each tab's name counting what it finds; it never reaches a tab marked
// `search: false` (Parameters, Joints, Animation), which reads no query. Escape or the X closes it.
it('searches every searchable tab at once from the row\'s icon, counting on each tab, never a tab it does not cover; Escape or the X closes it', () => {
  const onTab = vi.fn();
  const tabs = [{ id: 'parts', label: 'Parts', content: <Hits items={['R1', 'R2', 'C1']} /> }, { id: 'nets', label: 'Nets', content: <Hits items={['GND', 'R_NET']} /> },
    { id: 'notes', label: 'Notes', search: false, content: <Hits items={['R notes']} /> }];
  render(<Panel tabs={tabs} first="parts" onTab={onTab} />);
  fireEvent.click(searchIcon()!);
  expect(document.activeElement).toBe(box());
  // The row is the box, its X in the icon's place, and the tabs stand under it.
  expect([row().hasAttribute('data-searching'), searchIcon(), screen.getByRole('button', { name: 'Close search' }) !== null,
    row().firstElementChild!.contains(box()), screen.getByRole('tablist') !== null]).toEqual([true, null, true, true, true]);
  fireEvent.change(box()!, { target: { value: 'r' } });
  // Parts 2 and Nets 1 (each its own count), Notes none: its list reads no query.
  expect(tabNames()).toEqual(['Parts2', 'Nets1', 'Notes']);
  const sections = () => Object.fromEntries([...document.querySelectorAll<HTMLElement>('[data-flat-panel-section]')].map(section => [section.getAttribute('data-flat-panel-section'),
    [section.hidden, section.querySelector('ul')!.getAttribute('data-query'), section.querySelectorAll('li').length]]));
  expect(sections()).toEqual({ parts: [false, 'r', 2], nets: [true, 'r', 1], notes: [true, '', 1] });
  // A query that finds nothing in the open tab, something in another: that tab.
  fireEvent.change(box()!, { target: { value: 'gnd' } });
  expect(onTab).toHaveBeenLastCalledWith('nets');
  expect(tabNames()).toEqual(['Parts0', 'Nets1', 'Notes']);
  // Escape closes it: the tabs' row again, no counts, the icon back.
  fireEvent.keyDown(box()!, { key: 'Escape' });
  expect([box(), searchIcon() !== null, tabNames()]).toEqual([null, true, ['Parts', 'Nets', 'Notes']]);
  // Opened from a tab it does not cover, it opens the first it does; its X closes it.
  fireEvent.click(screen.getByRole('tab', { name: 'Notes' }));
  fireEvent.click(searchIcon()!);
  expect(onTab).toHaveBeenLastCalledWith('parts');
  fireEvent.click(screen.getByRole('button', { name: 'Close search' }));
  expect(box()).toBeNull();
});

// Where no tab is searchable (Parameters, Joints and Animation alone), there is no search icon, and / opens nothing.
it('has no search icon where no tab is searchable', () => {
  render(<Panel tabs={[{ id: 'parameters', label: 'Params', search: false, content: <p>p</p> }, { id: 'animation', label: 'Animation', search: false, content: <p>a</p> }]}
    first="parameters" focusSearch={0} />);
  expect([searchIcon(), document.querySelector('[data-flat-panel-search-open]')]).toEqual([null, null]);
});

// The tabs that do not fit go into ⋯, in order, the open tab always shown (in the last shown tab's place).
it('fits the tabs it can and puts the rest in ⋯, the open tab always shown', () => {
  const widths = new Map([['model', 50], ['params', 55], ['joints', 50], ['animation', 70]]);
  const ids = [...widths.keys()];
  expect(fitTabs({ ids, widths, room: 240, more: 28, gap: 2 })).toEqual({ visible: ids, hidden: [] });
  expect(fitTabs({ ids, widths, room: 180, more: 28, gap: 2, active: 'model' })).toEqual({ visible: ['model', 'params'], hidden: ['joints', 'animation'] });
  expect(fitTabs({ ids, widths, room: 180, more: 28, gap: 2, active: 'animation' })).toEqual({ visible: ['model', 'animation'], hidden: ['params', 'joints'] });
  expect(fitTabs({ ids, widths, room: 60, more: 28, gap: 2, active: 'animation' })).toEqual({ visible: ['animation'], hidden: ['model', 'params', 'joints'] });
});

// Drawn: the row's tabs at its left, ⋯ at its right directly before the search's icon, the room left over between the
// last tab and ⋯; ⋯ lists the hidden tabs with their icons; the open tab shows.
it('draws the tabs that fit at the left and ⋯ at the right beside the search, listing the rest with their icons', async () => {
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockImplementation(function (this: HTMLElement) {
    return this.hasAttribute('data-tab-ruler') ? ({ tree: 45, parameters: 52, position: 50, animation: 73 } as Record<string, number>)[this.getAttribute('data-tab-ruler')!]
      : this.hasAttribute('data-more-ruler') ? 28 : this.hasAttribute('data-flat-panel-tab-row') ? 160 : 0;
  });
  const tabs = [['tree', 'Model'], ['parameters', 'Params'], ['position', 'Joints'], ['animation', 'Animation']]
    .map(([id, label]) => ({ id, label, search: id === 'tree', content: <p>{label}</p> }));
  render(<Panel tabs={tabs} first="animation" />);
  // Model (45) and Animation (73) fit beside ⋯ (28 and its 4px) in 160px; Animation, open, in Params' place.
  expect(tabNames()).toEqual(['Model', 'Animation']);
  const line = row().querySelector<HTMLElement>('[data-flat-panel-tab-row]')!.parentElement!;
  const order = [...line.querySelectorAll('[role=tablist], [data-flat-panel-more], [data-flat-panel-search-open]')].map(node => node.getAttribute('role') ?? node.getAttribute('aria-label'));
  expect(order).toEqual(['tablist', 'More tabs', 'Search the board']);
  // The tablist takes the room (its tabs at its left), so ⋯ stands at the right, against the search's icon.
  expect([screen.getByRole('tablist').classList.contains('flex-1'), line.classList.contains('gap-1'), row().querySelector('[data-flat-panel-tab-row]')!.classList.contains('gap-1')]).toEqual([true, true, true]);
  fireEvent.pointerDown(screen.getByRole('button', { name: 'More tabs' }), { button: 0, ctrlKey: false, pointerType: 'mouse' });
  const menu = await screen.findByRole('menu', { name: 'More tabs' });
  expect(within(menu).getAllByRole('menuitem').map(item => [item.textContent, Boolean(item.querySelector('svg'))])).toEqual([['Params', true], ['Joints', true]]);
  fireEvent.click(within(menu).getByRole('menuitem', { name: 'Params' }));
  expect(screen.getByRole('tab', { name: 'Params' }).getAttribute('aria-selected')).toBe('true');
});

// A tab whose state is off its default carries a dot on its name, from the state its Reset is on by
// (`FlatPanelChanged`), its name saying ", changed"; a hidden one's dot is on its ⋯ item, and on ⋯.
it('marks a changed tab with a dot and ", changed", in the row and in ⋯, and ⋯ itself where a hidden tab is changed', async () => {
  vi.spyOn(HTMLElement.prototype, 'offsetWidth', 'get').mockImplementation(function (this: HTMLElement) {
    return this.hasAttribute('data-tab-ruler') ? 50 : this.hasAttribute('data-more-ruler') ? 28 : this.hasAttribute('data-flat-panel-tab-row') ? 140 : 0;
  });
  function Changing({ on }: { on: boolean }) { return <><button type="button" disabled={!on}>Reset</button><FlatPanelChanged on={on} /></>; }
  const tabs = (params: boolean, motion: boolean) => [{ id: 'tree', label: 'Model', content: <p>tree</p> },
    { id: 'parameters', label: 'Params', search: false, content: <Changing on={params} /> }, { id: 'animation', label: 'Animation', search: false, content: <Changing on={motion} /> }];
  const view = (params: boolean, motion: boolean) => <FlatPanel mode="docked" open onClose={() => {}} label="Panel" searchLabel="Search the board" tabs={tabs(params, motion)}
    tab="tree" onTabChange={() => {}} width={240} maxWidth={400} onWidthChange={() => {}} focusSearch={0} />;
  const { rerender } = render(view(false, false));
  // Model and Params shown (140px: two 50px tabs beside ⋯), Animation in ⋯.
  expect([screen.getAllByRole('tab').map(tab => tab.getAttribute('data-flat-panel-tab')), document.querySelector('[data-tool-changed]')]).toEqual([['tree', 'parameters'], null]);
  rerender(view(true, false));
  const params = screen.getByRole('tab', { name: 'Params, changed' });
  expect([params.hasAttribute('data-changed'), Boolean(params.querySelector('[data-tool-changed]')), document.querySelector('[data-flat-panel-more]')!.hasAttribute('data-changed')])
    .toEqual([true, true, false]);
  rerender(view(false, true));
  expect([screen.queryByRole('tab', { name: 'Params, changed' }), document.querySelector('[data-flat-panel-more]')!.hasAttribute('data-changed'),
    Boolean(document.querySelector('[data-flat-panel-more] [data-tool-changed]'))]).toEqual([null, true, true]);
  fireEvent.pointerDown(screen.getByRole('button', { name: 'More tabs' }), { button: 0, ctrlKey: false, pointerType: 'mouse' });
  const item = within(await screen.findByRole('menu', { name: 'More tabs' })).getByRole('menuitem', { name: 'Animation, changed' });
  expect(Boolean(item.querySelector('[data-tool-changed]'))).toBe(true);
});
