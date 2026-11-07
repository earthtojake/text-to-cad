import React from 'react';
import { act, cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ItemDetail, { CARD_RELATED_ROWS } from '../../../../dist/renderers/kit/inspector/ItemDetail.js';
import { InspectContext, hoverTipText } from '../../../../dist/renderers/kit/inspector/inspect.js';
import ReferenceChips from '../../../../dist/renderers/kit/tools/quick-edit/ReferenceChips.js';
import { ViewerHostContext } from '../../../../dist/host/context.js';
import { testHost } from '../../../../dist/host/testing/host.js';

Object.assign(globalThis, { React });
afterEach(cleanup);

// One pick as a view describes it: what it is, and a dozen of what it is connected to.
const rows = Array.from({ length: 12 }, (_, at) => ({ id: `row:${at}`, kind: 'face', pick: `#U3.${at + 1}`, label: `U3.${at + 1}`, detail: at ? '' : 'VBUS' }));
const item = { id: 'selected:#U3', pick: '#U3', kind: 'solid', title: 'U3', tip: 'ATmega328P', what: 'Part on the top side', ref: 'U3',
  facts: [{ label: 'Value', value: 'ATmega328P' }, { label: 'Mass', value: '2 g', section: 'Physical' }],
  related: { title: 'Pads of U3', count: '12 pads', rows } };

// What a reader reads of a detail, wherever it is drawn: its head, its line in words, its facts in
// their groups, its list's title and its rows' names.
const read = (root: HTMLElement) => ({
  head: root.querySelector('[data-detail-head]')!.textContent,
  what: root.querySelector('[data-flat-panel-selected-what]')!.textContent,
  facts: [...root.querySelectorAll('[data-flat-panel-facts] [data-info-row]')].map(row => row.textContent),
  section: root.querySelector('[data-detail-section]')!.getAttribute('aria-label'),
  title: root.querySelector('[data-flat-panel-detail-title]')!.textContent,
  rows: [...root.querySelectorAll('[data-item-detail-row]')].map(row => row.textContent),
});

it('the Selected pane and a chip\'s card are one component: an item reads the same in both, and their rows pick through the view', async () => {
  const inspect = { selected: ['#U3'], describe: () => item, select: vi.fn(), hover: vi.fn(), frame: vi.fn() };
  const host = testHost({ clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} } });
  const view = render(<ViewerHostContext.Provider value={host}><InspectContext.Provider value={inspect}>
    <div data-pane=""><ItemDetail item={item} copy="/board.kicad_pcb#U3" /></div>
    <ReferenceChips chips={[{ key: 'pick:#U3', label: 'U3', glyph: 'solid', id: 'U3', copy: '/board.kicad_pcb#U3', detail: item }]} />
  </InspectContext.Provider></ViewerHostContext.Provider>);
  // A touch's press opens the chip's card.
  const chip = view.container.querySelector<HTMLElement>('[data-quick-edit-ref] button')!;
  fireEvent.pointerDown(chip, { pointerType: 'touch' });
  fireEvent.click(chip);
  await act(async () => { await Promise.resolve(); });
  const pane = view.container.querySelector<HTMLElement>('[data-pane] [data-detail-place="pane"]')!;
  const card = document.querySelector<HTMLElement>('[data-quick-edit-ref-card] [data-detail-place="card"]')!;
  const inPane = read(pane), inCard = read(card);
  expect(inPane).toEqual({ head: 'U3', what: 'Part on the top side', facts: ['IDU3', 'ValueATmega328P', 'Mass2 g'], section: 'Physical',
    title: 'Pads of U312 pads', rows: rows.map(row => row.label + (row.detail || '')) });
  // The card reads the same, its list stopping after a few rows, the rest counted.
  expect({ ...inCard, rows: inCard.rows.length }).toEqual({ ...inPane, rows: CARD_RELATED_ROWS });
  expect(card.querySelector('[data-detail-more]')!.textContent).toBe(`+${rows.length - CARD_RELATED_ROWS} more`);
  // A row picks through the view, wherever it is drawn (Shift adds), lights on the pointer, and frames on a double-click.
  fireEvent.click(card.querySelector('[data-item-detail-row="row:1"]')!, { shiftKey: true });
  expect(inspect.select).toHaveBeenLastCalledWith('#U3.2', { multiSelect: true });
  fireEvent.mouseEnter(pane.querySelector('[data-item-detail-row="row:0"]')!.parentElement!);
  expect(inspect.hover).toHaveBeenLastCalledWith('#U3.1');
  fireEvent.doubleClick(pane.querySelector('[data-item-detail-row="row:0"]')!);
  expect(inspect.frame).toHaveBeenLastCalledWith(['#U3.1']);
  // The hover tip names it short, from the same item.
  expect(hoverTipText(item)).toBe('U3 · ATmega328P');
});
