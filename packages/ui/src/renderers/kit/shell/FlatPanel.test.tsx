import { useState } from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import FlatPanel from './FlatPanel.jsx';

// The Selected pane is 40% of the panel, whatever it holds; the person's height, once set, wins until a
// double-click on the separator clears it.
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

it('is 40% of the panel whatever it holds, with no ceiling, and keeps the height a person sets until a double-click resets it', () => {
  render(<Panel />);
  expect(height()).toBe('320px'); // 40% of 800, with 100px of content in it
  contentHeight = 40; remeasure();
  expect(height()).toBe('320px'); // what it holds does not size it: the lists above it stay put
  contentHeight = 900; remeasure();
  expect(height()).toBe('320px'); // it scrolls inside
  panelHeight = 1200; remeasure();
  expect(height()).toBe('480px'); // a tall panel, a tall pane
  panelHeight = 300; remeasure();
  expect(height()).toBe('120px');
  panelHeight = 200; remeasure();
  expect(height()).toBe('96px'); // never under the minimum
  panelHeight = 800; remeasure();

  expect(grip().getAttribute('aria-description')).toMatch(/Double-click/);
  fireEvent.keyDown(grip(), { key: 'ArrowUp' }); // a person's height: 320 + 16
  expect(height()).toBe('336px');
  panelHeight = 900; remeasure();
  expect(height()).toBe('336px'); // the panel no longer sizes it

  fireEvent.doubleClick(grip());
  expect(height()).toBe('360px'); // back to 40% of the panel
});

// "/" puts the keyboard in the search once per press: the panel closed and opened again, or mounted
// again, leaves the focus where it is, so the next V, M or P is a tool's key and not typed in the search.
it('focuses its search once for each press of /, never again when it reopens or remounts', () => {
  const panel = (open: boolean, focusSearch: number, key = 'a') => <FlatPanel key={key} mode="docked" open={open} onClose={() => {}} label="Panel" searchLabel="Search"
    tabs={[{ id: 'parts', label: 'Parts', content: <p>Parts</p> }]} tab="parts" onTabChange={() => {}} width={216} maxWidth={400}
    onWidthChange={() => {}} focusSearch={focusSearch} />;
  const { rerender } = render(panel(true, 0));
  const search = () => document.querySelector('[data-flat-panel-search] input, input[data-flat-panel-search]');
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
