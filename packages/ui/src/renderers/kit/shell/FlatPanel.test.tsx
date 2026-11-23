import { useEffect, useRef, useState } from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import FlatPanel, { FlatPanelChanged, fitTabs, useFlatPanel, useFlatPanelMatches } from './FlatPanel.jsx';
import { DEFAULT_PANEL_WIDTH } from './sidebars.js';

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
    onTabChange={(id: string) => { onTab(id); setTab(id); }} width={DEFAULT_PANEL_WIDTH} maxWidth={400} onWidthChange={() => {}} focusSearch={focusSearch} />;
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
    tab.classList.contains('text-muted-foreground'), Boolean(tab.querySelector('[data-flat-panel-tab-name].font-medium')), tab.classList.contains('h-control'), tab.classList.contains('px-1.5')]))
    .toEqual([['false', false, false, true, false, true, true], ['true', true, true, false, true, true, true]]);
  // 8px over and under the row; at its sides the inset (`--panel-inset`) less what its first and last boxes hang out by
  // (a pill's 6px, an icon button's: its 14px glyph centred in the control, 7px on a desktop), so a tab's name and the search's icon stand on the inset.
  expect([row().style.paddingTop, row().style.paddingBottom, row().style.paddingLeft, row().style.paddingRight])
    .toEqual(['8px', '8px', 'calc(var(--panel-inset) - 6px)', 'calc(var(--panel-inset) - calc((var(--cad-control) - 14px) / 2))']);
  expect([row().classList.contains('border-border'), row().hasAttribute('data-rule')]).toEqual([true, true]);
  // The row: the tab row (its tablist taking the room), then the search's icon, last; no ⋯, no search box.
  const line = row().firstElementChild as HTMLElement;
  expect([...line.children].map(child => child.getAttribute('data-flat-panel-tab-row') !== null ? 'tabs' : child.getAttribute('aria-label'))).toEqual(['tabs', 'Search the board']);
  expect([document.querySelector('[data-flat-panel-more]'), box(), document.querySelector('[data-flat-panel-body] [data-flat-panel-search]')]).toEqual([null, null, null]);
  expect(screen.getByRole('tablist').classList.contains('flex-1')).toBe(true);
  expect(document.querySelector('aside[data-flat-panel]')!.getAttribute('style')).toMatch(/width: 232px/);
});

// One tab is a plain title in the tab's place: no pill, no fill, on the tabs' 32px row with 8px over it, and no rule and
// no gap under it (nothing to separate); several tabs add the rule and 8px under. The search's icon at the row's right end.
it('draws a single tab as a plain title on the tabs\' row with no rule under it, the search an icon at the right, and several as pills over a rule', () => {
  render(<Panel tabs={[{ id: 'model', label: 'Model', content: <p>tree</p> }]} first="model" />);
  const title = row().querySelector<HTMLElement>('[data-flat-panel-heading]')!;
  expect([screen.queryAllByRole('tab').length, screen.queryByRole('tablist'), title.textContent]).toEqual([0, null, 'Model']);
  // Its name on the inset, as a tab's is: the title pads as a pill does (6px), the row the inset less that.
  expect([title.classList.contains('font-medium'), title.classList.contains('px-1.5'), title.classList.contains('h-control')]).toEqual([true, true, true]);
  const block = () => [row().classList.contains('border-border'), row().hasAttribute('data-compact'), row().style.height === 'calc(var(--cad-control) + 4px)',
    [row().style.paddingTop, row().style.paddingBottom, row().style.paddingLeft], document.querySelector('[data-flat-panel-body]')!.className];
  const one = block();
  expect(one.slice(0, 4)).toEqual([false, false, true, ['8px', '0px', 'calc(var(--panel-inset) - 6px)']]);
  expect([...row().children].map(child => child.getAttribute('aria-label') ?? child.tagName.toLowerCase())).toEqual(['h2', 'Search the board']);
  expect(document.querySelector('[data-flat-panel-section="model"]')!.getAttribute('aria-labelledby')).toBe(title.id);
  cleanup();
  render(<Panel tabs={[{ id: 'parts', label: 'Parts', content: <p>Parts</p> }, { id: 'nets', label: 'Nets', content: <p>Nets</p> }]} first="parts" />);
  expect([screen.getAllByRole('tab').length, document.querySelector('[data-flat-panel-heading]'), block()]).toEqual([2, null, [true, false, true, ['8px', '8px', 'calc(var(--panel-inset) - 6px)'], one[4]]]);
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

// A tab's hits as a tree draws them: its rows filtered by the panel's query (its count told), a press on one a pick,
// and the arrows walking them while the panel hands it the keys (`keyed`), as `useTreeSearch` does: an arrow past its
// end answers false, Home and End put the cursor on its first and last hit.
function Walk({ items, onPick = () => {} }: { items: string[], onPick?: (item: string) => void }) {
  const panel = useFlatPanel()!;
  const query = panel.query.trim().toLowerCase();
  const found = query ? items.filter(item => item.toLowerCase().includes(query)) : items;
  useFlatPanelMatches(query ? found.length : null);
  const [cursor, setCursor] = useState(0);
  useEffect(() => setCursor(0), [query]);
  const keys = useRef<(event: { key: string }) => boolean>(() => false);
  keys.current = event => {
    if (event.key === 'Home' || event.key === 'End') { setCursor(event.key === 'Home' ? 0 : found.length - 1); return true; }
    const next = cursor + ({ ArrowDown: 1, ArrowUp: -1 } as Record<string, number>)[event.key];
    if (Number.isNaN(next) || next < 0 || next >= found.length) return false;
    setCursor(next);
    return true;
  };
  useEffect(() => panel.registerKeys((event: { key: string }) => keys.current(event)), [panel.registerKeys]);
  return <ul data-query={query}>{found.map((item, at) => <li key={item} data-cursor={panel.keyed !== false && query && at === cursor ? '' : undefined}>
    <button type="button" onClick={() => onPick(item)}>{item}</button></li>)}</ul>;
}
const section = (id: string) => document.querySelector<HTMLElement>(`[data-flat-panel-section="${id}"]`)!;
const shownSections = () => [...document.querySelectorAll<HTMLElement>('[data-flat-panel-section]')].filter(node => !node.hidden).map(node => node.getAttribute('data-flat-panel-section'));
const cursorAt = () => [...document.querySelectorAll('[data-cursor]')].map(node => node.textContent);
const headBox = () => ({ compact: row().hasAttribute('data-compact'), rule: row().classList.contains('border-border'), height: row().style.height,
  padding: [row().style.paddingTop, row().style.paddingBottom, row().style.paddingLeft, row().style.paddingRight] });

// The search's icon (or /) makes the head's row the search box: the same row, its padding, height and rule as they
// were, no tabs; an empty box changes nothing in the body. A query shows results alone: where several tabs are
// searched, ONE list, a group per tab that finds something, in the tabs' order, under its name and count; the arrows
// walk the groups in order; a press on a hit is its pick. Nothing found, one line. Closed, the tab that was open.
it('turns the head\'s row into the search box, results grouped by tab across the tree-like tabs, the arrows walking them in order; closed, the tab that was open', () => {
  const onTab = vi.fn(), onPick = vi.fn();
  const tabs = [{ id: 'parts', label: 'Parts', content: <Walk items={['R1', 'R2', 'C1']} onPick={onPick} /> }, { id: 'nets', label: 'Nets', content: <Walk items={['GND', 'R_NET']} onPick={onPick} /> },
    { id: 'layers', label: 'Layers', content: <Walk items={['B.Cu', 'F.Cu']} /> }, { id: 'notes', label: 'Notes', search: false, content: <Walk items={['R notes']} /> }];
  render(<Panel tabs={tabs} first="notes" onTab={onTab} />);
  const head = headBox();
  fireEvent.click(searchIcon()!);
  // One row: the box, the X in the icon's place; no tabs; the row's box as it was; the body as it was (Notes).
  expect([document.activeElement === box(), screen.queryByRole('tablist'), screen.getByRole('button', { name: 'Close search' }) !== null, headBox(), shownSections()])
    .toEqual([true, null, true, head, ['notes']]);
  fireEvent.change(box()!, { target: { value: 'r' } });
  // Parts 2 and Nets 1, each under its name and count; the Layers find none (no group); Notes is not searched.
  expect([shownSections(), [...document.querySelectorAll('[data-flat-panel-group-heading]')].map(heading => heading.textContent)])
    .toEqual([['parts', 'nets'], ['Parts2', 'Nets1']]);
  expect([section('notes').querySelector('ul')!.getAttribute('data-query'), section('parts').getAttribute('role')]).toEqual(['', null]);
  // The arrows: Parts' hits, then on past their end into the Nets', and back up into the Parts' last.
  expect(cursorAt()).toEqual(['R1']);
  fireEvent.keyDown(box()!, { key: 'ArrowDown' });
  fireEvent.keyDown(box()!, { key: 'ArrowDown' });
  expect(cursorAt()).toEqual(['R_NET']);
  fireEvent.keyDown(box()!, { key: 'ArrowUp' });
  expect(cursorAt()).toEqual(['R2']);
  // A hit is its tab's: a press picks it, no tab chosen for it.
  fireEvent.click(within(section('nets')).getByRole('button', { name: 'R_NET' }));
  expect([onPick.mock.calls, onTab.mock.calls]).toEqual([[['R_NET']], []]);
  // Nothing found anywhere: one line.
  fireEvent.change(box()!, { target: { value: 'zzz' } });
  expect([shownSections(), document.querySelectorAll('[data-flat-panel-empty]').length]).toEqual([[], 1]);
  // Escape closes it: the tabs again, on Notes, as before; nothing chose a tab meanwhile.
  fireEvent.keyDown(box()!, { key: 'Escape' });
  expect([box(), screen.getByRole('tab', { selected: true }).querySelector('[data-flat-panel-tab-name]')!.textContent, shownSections(), headBox(), onTab.mock.calls]).toEqual([null, 'Notes', ['notes'], head, []]);
});

// One tree-like tab (a model's Model beside its Joints): a query shows that tree's hits, whatever tab was open, and
// clearing it shows that tab again; a single tab's title row becomes the box as it is, the head's one block.
it('searches the one tree from any tab and gives the open tab back as the query clears; a lone title\'s row is the box\'s, unchanged', () => {
  const onTab = vi.fn();
  render(<Panel tabs={[{ id: 'tree', label: 'Model', content: <Walk items={['base', 'arm']} /> }, { id: 'joints', label: 'Joints', search: false, content: <p>pose</p> }]}
    first="joints" onTab={onTab} />);
  fireEvent.click(searchIcon()!);
  expect(shownSections()).toEqual(['joints']);
  fireEvent.change(box()!, { target: { value: 'ar' } });
  expect([shownSections(), section('tree').querySelectorAll('li').length, document.querySelector('[data-flat-panel-group-heading]')]).toEqual([['tree'], 1, null]);
  fireEvent.change(box()!, { target: { value: '' } });
  expect(shownSections()).toEqual(['joints']);
  fireEvent.click(screen.getByRole('button', { name: 'Close search' }));
  expect([box(), screen.getByRole('tab', { selected: true }).querySelector('[data-flat-panel-tab-name]')!.textContent, onTab.mock.calls]).toEqual([null, 'Joints', []]);
  cleanup();
  render(<Panel tabs={[{ id: 'layers', label: 'Layers', content: <Walk items={['CUT', 'BEND']} /> }]} first="layers" />);
  const title = headBox();
  fireEvent.click(searchIcon()!);
  expect([title.compact, title.rule, title.height, headBox(), row().querySelector('[data-flat-panel-heading]')]).toEqual([false, false, 'calc(var(--cad-control) + 4px)', title, null]);
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
    tab="tree" onTabChange={() => {}} width={DEFAULT_PANEL_WIDTH} maxWidth={400} onWidthChange={() => {}} focusSearch={0} />;
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
