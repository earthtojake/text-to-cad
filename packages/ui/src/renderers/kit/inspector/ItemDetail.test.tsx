import React from 'react';
import { act, cleanup, fireEvent, render } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import { InspectContext, hoverTipText } from '../../../../dist/renderers/kit/inspector/inspect.js';
import ReferenceChips from '../../../../dist/renderers/kit/tools/quick-edit/ReferenceChips.js';
import { ViewerHostContext } from '../../../../dist/host/context.js';
import { testHost } from '../../../../dist/host/testing/host.js';

Object.assign(globalThis, { React });
afterEach(cleanup);

// One pick as a view describes it: what it is and a few key facts.
const item = { id: 'selected:#U3', pick: '#U3', kind: 'solid', title: 'U3', tip: 'ATmega328P',
  facts: [{ label: 'Value', value: 'ATmega328P' }, { label: 'Mass', value: '2 g' }] };

it('a chip\'s card is the pick in focus alone: its name as the heading copying its reference, then its facts as one grid of labels and left-aligned values', async () => {
  const copied: string[] = [];
  const host = testHost({ clipboard: { writeText: async (text: string) => { copied.push(text); }, readText: async () => '', writeImage: async () => {} } });
  const view = render(<ViewerHostContext.Provider value={host}><InspectContext.Provider value={{ describe: () => item, data: 'board' }}>
    <ReferenceChips chips={[{ key: 'pick:#U3', label: 'U3', glyph: 'solid', copy: '/board.kicad_pcb#U3', detail: item }]} />
  </InspectContext.Provider></ViewerHostContext.Provider>);
  // A touch's press opens the chip's card.
  const chip = view.container.querySelector<HTMLElement>('[data-quick-edit-ref] button')!;
  fireEvent.pointerDown(chip, { pointerType: 'touch' });
  fireEvent.click(chip);
  await act(async () => { await Promise.resolve(); });
  const card = document.querySelector<HTMLElement>('[data-quick-edit-ref-card] [data-detail-card]')!;
  const grid = card.querySelector<HTMLElement>('[data-detail-facts]')!;
  expect({
    head: card.querySelector('[data-board-detail-head]')!.textContent,
    facts: [...grid.querySelectorAll('[data-info-row]')].map(row => [row.querySelector('dt')!.textContent, row.querySelector('dd')!.textContent]),
    grid: grid.className.includes('grid-cols-[4.5rem_minmax(0,1fr)]'),
    rows: card.querySelectorAll('[data-tree-row]').length,
  }).toEqual({ head: 'U3', facts: [['Value', 'ATmega328P'], ['Mass', '2 g']], grid: true, rows: 0 });
  // The heading is the copy: its icon at the row's right end copies the whole reference.
  copied.length = 0;
  fireEvent.click(card.querySelector<HTMLElement>('[aria-label="Copy reference U3"]')!);
  await act(async () => { await Promise.resolve(); });
  expect(copied).toEqual(['/board.kicad_pcb#U3']);
  // The hover tip names it short, from the same item.
  expect(hoverTipText(item)).toBe('U3 · ATmega328P');
});
