import { useState } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import FlatPanel from './FlatPanel.jsx';

// The Selected pane fits its content up to min(320px, 40% of the panel); the person's height, once
// dragged, wins until a double-click on the separator clears it.
let panelHeight = 800, contentHeight = 100;
const observers = new Set<() => void>();
const remeasure = () => act(() => { observers.forEach(callback => callback()); });
const rect = Element.prototype.getBoundingClientRect;
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class {
    callback: () => void;
    constructor(callback: () => void) { this.callback = callback; }
    observe() { observers.add(this.callback); } unobserve() {} disconnect() { observers.delete(this.callback); }
  });
  Element.prototype.getBoundingClientRect = function (this: Element) {
    const height = this.hasAttribute('data-flat-panel') ? panelHeight : this.querySelector(':scope > [data-content]') ? contentHeight : 0;
    return DOMRect.fromRect({ x: 0, y: 0, width: 216, height });
  };
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); Element.prototype.getBoundingClientRect = rect; panelHeight = 800; contentHeight = 100; });

function Panel() {
  const [kept, setKept] = useState<number | null>(null);
  return <FlatPanel mode="docked" open onClose={() => {}} label="Panel" searchLabel="Search" tabs={[{ id: 'parts', label: 'Parts', content: <p>Parts</p> }]}
    tab="parts" onTabChange={() => {}} width={216} maxWidth={400} onWidthChange={() => {}} focusSearch={0}
    detail={<div data-content="" />} detailHeight={kept} onDetailHeightChange={next => setKept(next ?? null)} />;
}
const pane = () => document.querySelector<HTMLElement>('[data-flat-panel-detail]')!;
const height = () => pane().style.height;
const grip = () => screen.getByRole('separator', { name: 'Resize details' });

it('fits its content under the cap, caps at min(320px, 40% of the panel), and keeps the height a person drags', () => {
  render(<Panel />);
  expect(height()).toBe('101px'); // 100px of content and the pane's top rule
  contentHeight = 150; remeasure();
  expect(height()).toBe('151px');
  contentHeight = 40; remeasure();
  expect(height()).toBe('96px'); // never under the minimum
  contentHeight = 900; remeasure();
  expect(height()).toBe('320px'); // 40% of 800 is 320; scrolls inside past it
  panelHeight = 600; remeasure();
  expect(height()).toBe('240px'); // 40% of 600
  panelHeight = 800; contentHeight = 150; remeasure();

  expect(grip().getAttribute('aria-description')).toMatch(/Double-click/);
  fireEvent.keyDown(grip(), { key: 'ArrowUp' }); // a person's height: 151 + 16
  expect(height()).toBe('167px');
  contentHeight = 300; remeasure();
  expect(height()).toBe('167px'); // content no longer resizes it

  fireEvent.doubleClick(grip());
  expect(height()).toBe('301px'); // back to fitting
});
