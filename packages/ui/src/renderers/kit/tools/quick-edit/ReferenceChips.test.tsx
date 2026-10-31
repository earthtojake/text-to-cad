import React from 'react';
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import ReferenceChips from '../../../../../dist/renderers/kit/tools/quick-edit/ReferenceChips.js';
import { InfoRow } from '../../../../../dist/renderers/kit/inspector/referenceRows.js';
import { ViewerHostContext } from '../../../../../dist/host/context.js';
import { testHost } from '../../../../../dist/host/testing/host.js';
import { ViewerMobileContext } from '../../../../../dist/file-viewer/responsive.js';

Object.assign(globalThis, { React });
afterEach(() => { cleanup(); vi.useRealTimers(); vi.unstubAllGlobals(); });
// A hint measures its trigger.
const measured = () => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });

const chip = (n: number, extra = {}) => ({ key: `run:${n}`, label: `base · face ${n}`, id: `f:base.make_box1.${n}`, copy: `/models/base.step#f:base.make_box1.${n}`,
  card: <InfoRow label="Area" title="Face area">{`${n * 10} mm²`}</InfoRow>, ...extra });
function mount(chips: any[], mobile = false) {
  const copied: string[] = [];
  const host = testHost({ clipboard: { writeText: async (text: string) => { copied.push(text); }, readText: async () => '', writeImage: async () => {} } });
  render(<ViewerMobileContext.Provider value={mobile}><ViewerHostContext.Provider value={host}><ReferenceChips chips={chips} /></ViewerHostContext.Provider></ViewerMobileContext.Provider>);
  return copied;
}
const settle = () => act(async () => { await Promise.resolve(); });

it('a click on a chip copies its reference and says so in its place; a touch opens its card, its ID first, and a click on a value copies the value', async () => {
  const onHover = vi.fn();
  const copied = mount([chip(3, { onHover })]);
  const label = screen.getByRole('button', { name: 'base · face 3' });
  // A mouse click copies, and says "Copied" where the label was; it opens no card (a rest of the pointer does).
  fireEvent.pointerDown(label, { pointerType: 'mouse' });
  fireEvent.click(label);
  await settle();
  expect(copied).toEqual(['/models/base.step#f:base.make_box1.3']);
  expect(label.textContent).toBe('Copied');
  expect(document.querySelector('[data-quick-edit-ref-card]')).toBeNull();
  // A touch's press opens the card too: its name, its id, then the renderer's rows.
  fireEvent.pointerDown(label, { pointerType: 'touch' });
  fireEvent.click(label);
  await settle();
  const card = document.querySelector<HTMLElement>('[data-quick-edit-ref-card="run:3"]')!;
  expect([...card.querySelectorAll('[data-info-row]')].map(row => row.textContent)).toEqual(['IDf:base.make_box1.3', 'Area30 mm²']);
  const value = card.querySelectorAll<HTMLElement>('[data-info-row] > div')[1];
  expect(value.className).toContain('cursor-pointer');
  fireEvent.click(value);
  await settle();
  expect(copied.at(-1)).toBe('30 mm²');
  // "Copied" is drawn over the value, which stays in place unseen: the row keeps its height.
  expect(value.hasAttribute('data-copied')).toBe(true);
  expect(value.firstElementChild!.className).toContain('invisible');
  expect(value.firstElementChild!.textContent).toBe('30 mm²');
  expect(value.lastElementChild!.textContent).toBe('Copied');
  // Its title copies the reference, as the chip does, its icon a tick for a moment.
  const title = within(card).getByRole('button', { name: 'Copy reference base · face 3' });
  fireEvent.click(title);
  await settle();
  expect(copied.at(-1)).toBe('/models/base.step#f:base.make_box1.3');
  expect(title.hasAttribute('data-copied')).toBe(true);
  expect(title.querySelector('svg.lucide-check')).not.toBeNull();
});

it('past the first few, the rest are one "+N more" chip: a narrow list whose rows copy, remove and light their picks like chips', async () => {
  const onRemove = vi.fn(), onHover = vi.fn();
  const copied = mount([1, 2, 3, 4, 5, 6].map(n => chip(n, n === 6 ? { onRemove, onHover } : {})));
  const box = screen.getByLabelText('References');
  expect(within(box).getAllByRole('button').map(button => button.textContent))
    .toEqual(['base · face 1', 'base · face 2', 'base · face 3', 'base · face 4', '+2 more']);
  fireEvent.click(screen.getByRole('button', { name: '+2 more' }));
  const list = within(screen.getByRole('dialog', { name: 'More references' }));
  const row = list.getByRole('button', { name: 'base · face 6' });
  fireEvent.pointerEnter(row.closest('li')!, { pointerType: 'mouse' });
  expect(onHover).toHaveBeenLastCalledWith(true);
  fireEvent.pointerDown(row, { pointerType: 'mouse' });
  fireEvent.click(row);
  await settle();
  expect(copied).toEqual(['/models/base.step#f:base.make_box1.6']);
  fireEvent.click(list.getByRole('button', { name: 'Remove base · face 6' }));
  expect(onRemove).toHaveBeenCalledOnce();
});


it('without a host clipboard nothing offers a copy', () => {
  render(<ReferenceChips chips={[chip(1)]} />);
  expect(screen.getByRole('button', { name: 'base · face 1' }).className).not.toContain('cursor-pointer');
});

it('on a phone a tap on a chip opens its card above it and copies nothing; the card\'s title copies', async () => {
  const copied = mount([chip(4)], true);
  const label = screen.getByRole('button', { name: 'base · face 4' });
  fireEvent.pointerDown(label, { pointerType: 'touch' });
  fireEvent.click(label);
  await settle();
  const card = document.querySelector<HTMLElement>('[data-quick-edit-ref-card]')!;
  expect([copied, card.getAttribute('data-side')]).toEqual([[], 'top']);
});

it("a card's ID is one monospace line, its middle cut where it is long, the whole of it its hint; a click on it copies the chip's whole reference", async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  measured();
  const id = 'L bracket 80 x 60 x 6 mm/f:bracket_body.body_efhphp2~7f355a89aedf';
  const reference = `/work/bracket.step#${id}`;
  const copied = mount([chip(1, { label: 'L bracket 80 x 60 x 6 mm · face 1', id, copy: reference })]);
  const label = screen.getByRole('button', { name: 'L bracket 80 x 60 x 6 mm · face 1' });
  fireEvent.pointerDown(label, { pointerType: 'touch' });
  fireEvent.click(label);
  await settle();
  const value = document.querySelector<HTMLElement>('[data-chip-id]')!;
  expect(value.textContent).toBe('L bracket 80 x…~7f355a89aedf');
  expect(value.className).toMatch(/\bwhitespace-nowrap\b/);
  expect(value.className).toMatch(/\bfont-mono\b/);
  expect(value.hasAttribute('title')).toBe(false);
  fireEvent.pointerMove(value, { pointerType: 'mouse' });
  act(() => { vi.advanceTimersByTime(450); });
  expect(screen.getByRole('tooltip').textContent).toBe(id);
  fireEvent.click(value);
  await settle();
  // The same text the chip's press (first) and its title's copy icon (last) copy.
  fireEvent.click(screen.getByRole('button', { name: 'Copy reference L bracket 80 x 60 x 6 mm · face 1' }));
  await settle();
  expect(copied).toEqual([reference, reference, reference]);
  // A short id is shown whole, with no hint.
  cleanup();
  mount([chip(2)]);
  fireEvent.pointerDown(screen.getByRole('button', { name: 'base · face 2' }), { pointerType: 'touch' });
  fireEvent.click(screen.getByRole('button', { name: 'base · face 2' }));
  await settle();
  expect(document.querySelector('[data-chip-id]')!.textContent).toBe('f:base.make_box1.2');
});

it("a chip's part name is cut at sixteen characters, the number after it whole; a document of one part shows the kind and number alone", async () => {
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] });
  measured();
  const long = 'L bracket 80 x 60 x 6 mm';
  mount([
    chip(1, { label: `${long} · face 12`, compact: { name: long, kind: 'face', number: '12' } }),
    chip(2, { label: `${long} · face 3`, compact: { kind: 'face', number: '3', words: 'face 3' } }),
    // A whole part's chip with no card: its whole name is its hint.
    { key: 'part', label: long, glyph: 'solid' },
  ]);
  const shown = (name: string) => screen.getByRole('button', { name }).textContent;
  expect([shown(`${long} · face 12`), shown(`${long} · face 3`), shown(long)]).toEqual(['L bracket 80 x…12', 'face 3', 'L bracket 80 x…']);
  expect(document.querySelector('[data-chip-name]')!.textContent!.length).toBeLessThanOrEqual(16);
  fireEvent.pointerMove(screen.getByRole('button', { name: long }).querySelector('[data-chip-name]')!, { pointerType: 'mouse' });
  act(() => { vi.advanceTimersByTime(450); });
  expect(screen.getByRole('tooltip').textContent).toBe(long);
});
