import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { SliderField } from '../../../../dist/renderers/kit/inspector/SliderField.js';

Object.assign(globalThis, { React });
// The slider primitive measures its thumb; jsdom has no PointerEvent, which the label's scrub reads.
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.stubGlobal('PointerEvent', class extends MouseEvent {
    pointerId: number; pointerType: string;
    constructor(type: string, init: PointerEventInit = {}) { super(type, init); this.pointerId = init.pointerId ?? 1; this.pointerType = init.pointerType ?? 'mouse'; }
  });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

type Props = Partial<React.ComponentProps<typeof SliderField>>;
// A parameter as the Params tab draws it: 3 to 9 mm on a 0.1 step, at 7.3.
function hole(props: Props = {}) {
  const onValueChange = vi.fn(), onTextCommit = vi.fn(), onValueCommit = vi.fn();
  const view = render(<SliderField label="hole_d" name="hole_d" value={7.3} min={3} max={9} step={0.1} text="7.3 mm"
    onValueChange={onValueChange} onValueCommit={onValueCommit} onTextCommit={onTextCommit} textLabel="hole_d value" {...props} />);
  const input = screen.getByRole('textbox', { name: 'hole_d value' }) as HTMLInputElement;
  const box = input.closest('[data-slider-field-value-box]') as HTMLElement;
  return { ...view, input, box, onValueChange, onTextCommit, onValueCommit };
}
const hint = () => document.querySelector('[data-slider-field-hint]');
// A press on the field as a pointer makes it: down, the focus it gives, up.
const press = (input: HTMLInputElement) => {
  fireEvent.pointerDown(input);
  if (document.activeElement !== input) act(() => input.focus());
  fireEvent.mouseUp(input);
};

it('is a label, a number field with its unit after it, and a slider, in that order, with no icon', () => {
  const { container, input, box } = hole();
  const root = container.querySelector('[data-slider-field]')!;
  const label = root.querySelector('[data-slider-field-label]')!;
  const thumb = screen.getByRole('slider', { name: 'hole_d' });
  // The number is what is edited; the unit is drawn after it, muted, never part of the input.
  expect([label.textContent, input.value, box.querySelector('[data-slider-field-unit]')!.textContent, thumb.getAttribute('aria-valuenow')])
    .toEqual(['hole_d', '7.3', 'mm', '7.3']);
  expect(box.querySelector('[data-slider-field-unit]')!.className).toContain('text-muted-foreground');
  expect(label.compareDocumentPosition(input) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(input.compareDocumentPosition(thumb) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(root.querySelector('svg')).toBeNull();
  // As wide as what it holds (22px tall, 32px at least, 96 at most), so a longer value grows it to the left from the
  // slider's right edge; no fill at rest, an outline under the pointer, the brand's edge edited, each 6px off the text.
  // In a panel its text ends on the panel's inset, where the track ends: its box hangs past by its own 7px (6px and its edge).
  for (const name of ['h-[calc(var(--cad-icon-button)-2px)]', 'w-max', 'min-w-8', 'max-w-24', 'bg-transparent', 'px-1.5', 'hover:border-foreground/20', 'data-[editing]:border-brand']) expect(box.className).toContain(name);
  expect(box.className).not.toMatch(/(^|\s)bg-foreground\//);
  expect(box.className.split(' ')).toContain('-mr-[7px]');
  press(input);
  expect(box.hasAttribute('data-editing')).toBe(true);
});

it('selects the number on the first click, places the caret on a later one', () => {
  const { input } = hole();
  press(input);
  expect([input.selectionStart, input.selectionEnd]).toEqual([0, 3]);
  input.setSelectionRange(1, 1);
  press(input);
  expect([input.selectionStart, input.selectionEnd]).toEqual([1, 1]);
});

it('commits on Enter or blur in its unit, puts back what it held on Escape, and commits nothing left as it shows', () => {
  const { input, onTextCommit, onValueChange } = hole();
  press(input);
  fireEvent.change(input, { target: { value: '8.25' } });
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(onTextCommit).toHaveBeenLastCalledWith('8.25 mm');
  press(input);
  fireEvent.change(input, { target: { value: '4' } });
  fireEvent.blur(input);
  expect(onTextCommit).toHaveBeenLastCalledWith('4 mm');
  onTextCommit.mockClear(); onValueChange.mockClear();
  press(input);
  fireEvent.change(input, { target: { value: '5' } });
  fireEvent.keyDown(input, { key: 'Escape' });
  expect(onTextCommit).not.toHaveBeenCalled();
  // The slider followed 5, and is put back where it was.
  expect(onValueChange.mock.calls).toEqual([[5], [7.3]]);
  expect(input.value).toBe('7.3');
  press(input);
  fireEvent.blur(input);
  expect(onTextCommit).not.toHaveBeenCalled();
});

// A value tabbed through or clicked and left as it shows writes nothing back: its text is rounded
// (a joint at 123.4° shows 123°), and committing it would move the value and drop a named pose.
it('commits nothing for the rounded number it shows, and moves nothing while it is typed again', () => {
  const onTextCommit = vi.fn(), onValueChange = vi.fn();
  render(<SliderField label="Elbow" name="Elbow" value={123.4} min={0} max={180}
    onValueChange={onValueChange} text="123°" onTextCommit={onTextCommit} textLabel="Elbow value" />);
  const value = screen.getByRole('textbox', { name: 'Elbow value' }) as HTMLInputElement;
  fireEvent.focus(value);
  fireEvent.blur(value);
  fireEvent.focus(value);
  fireEvent.change(value, { target: { value: '12' } });
  fireEvent.change(value, { target: { value: '123' } });
  fireEvent.blur(value);
  expect(onTextCommit).not.toHaveBeenCalled();
  expect(onValueChange.mock.calls).toEqual([[12], [123.4]]);
  fireEvent.focus(value);
  fireEvent.change(value, { target: { value: '90' } });
  fireEvent.blur(value);
  expect(onTextCommit).toHaveBeenCalledWith('90°');
});

it('steps by the step on Up and Down, ten of them with Shift, within the range, the slider following', () => {
  const { input, onValueChange, onTextCommit } = hole();
  press(input);
  fireEvent.keyDown(input, { key: 'ArrowUp' });
  expect(input.value).toBe('7.4');
  fireEvent.keyDown(input, { key: 'ArrowDown', shiftKey: true });
  expect(input.value).toBe('6.4');
  fireEvent.keyDown(input, { key: 'ArrowUp', shiftKey: true });
  fireEvent.keyDown(input, { key: 'ArrowUp', shiftKey: true });
  expect(input.value).toBe('8.4');
  fireEvent.keyDown(input, { key: 'ArrowUp', shiftKey: true });
  expect(input.value).toBe('9.0');
  expect(onValueChange.mock.calls.map(([value]) => value)).toEqual([7.4, 6.4, 7.4, 8.4, 9]);
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(onTextCommit).toHaveBeenLastCalledWith('9.0 mm');
});

it('converts a length typed in another unit, and says an unknown unit and goes back on Enter', () => {
  const { input, box, onTextCommit, onValueChange } = hole({ max: 40 });
  press(input);
  fireEvent.change(input, { target: { value: '1 in' } });
  expect(onValueChange).toHaveBeenLastCalledWith(25.4);
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(onTextCommit).toHaveBeenLastCalledWith('25.4 mm');
  onTextCommit.mockClear();
  press(input);
  fireEvent.change(input, { target: { value: '5 kg' } });
  expect(box.hasAttribute('data-invalid')).toBe(true);
  expect(hint()?.textContent).toContain('Unknown unit: kg');
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(onTextCommit).not.toHaveBeenCalled();
  expect(input.value).toBe('7.3');
  expect(hint()).toBeNull();
});

it('says the bound a number is past, and sets it on Enter', () => {
  const { input, box, onTextCommit, onValueChange } = hole();
  press(input);
  fireEvent.change(input, { target: { value: '50' } });
  expect(hint()?.textContent).toContain('Max 9 mm');
  expect(hint()?.getAttribute('data-hint-kind')).toBe('range');
  expect(box.hasAttribute('data-invalid')).toBe(false);
  // The slider follows it as far as it goes.
  expect(onValueChange).toHaveBeenLastCalledWith(9);
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(onTextCommit).toHaveBeenLastCalledWith('9.0 mm');
  press(input);
  fireEvent.change(input, { target: { value: '1' } });
  expect(hint()?.textContent).toContain('Min 3 mm');
});

it('outlines what is no number in red with a hint, and puts the value back', () => {
  const { input, box, onTextCommit } = hole();
  press(input);
  fireEvent.change(input, { target: { value: 'abc' } });
  expect([box.hasAttribute('data-invalid'), input.getAttribute('aria-invalid')]).toEqual([true, 'true']);
  expect(box.className).toContain('data-[invalid]:border-destructive');
  expect(hint()?.textContent).toContain('Enter a number, 3–9 mm');
  fireEvent.blur(input);
  expect(onTextCommit).not.toHaveBeenCalled();
  expect([input.value, box.hasAttribute('data-invalid')]).toEqual(['7.3', false]);
});

it('follows a typed value live in the slider\'s own scale (a percentage of 0–1)', () => {
  const onValueChange = vi.fn(), onTextCommit = vi.fn();
  render(<SliderField label="Zones" name="Zone opacity" value={0.6} min={0} max={1} step={0.01} scale={100}
    onValueChange={onValueChange} text="60%" onTextCommit={onTextCommit} textLabel="Zone opacity value" />);
  const input = screen.getByRole('textbox', { name: 'Zone opacity value' }) as HTMLInputElement;
  press(input);
  fireEvent.change(input, { target: { value: '25' } });
  expect(onValueChange).toHaveBeenLastCalledWith(0.25);
  fireEvent.change(input, { target: { value: '150' } });
  expect(hint()?.textContent).toContain('Max 100%');
  fireEvent.keyDown(input, { key: 'Enter' });
  expect(onTextCommit).toHaveBeenLastCalledWith('100%');
  // The slider still writes through `onValueChange`.
  fireEvent.keyDown(screen.getByRole('slider', { name: 'Zone opacity' }), { key: 'ArrowRight' });
  expect(onValueChange).toHaveBeenLastCalledWith(0.61);
});

it('scrubs from its label: a step a pixel, ten with Shift, within the range, committed as it ends', () => {
  const { container, onValueChange, onValueCommit } = hole();
  const label = container.querySelector('[data-slider-field-label]') as HTMLElement;
  expect(label.className).toContain('cursor-ew-resize');
  fireEvent.pointerDown(label, { clientX: 100, button: 0 });
  fireEvent.pointerMove(label, { clientX: 101 });
  expect(onValueChange).not.toHaveBeenCalled();
  fireEvent.pointerMove(label, { clientX: 105 });
  expect(onValueChange).toHaveBeenLastCalledWith(7.8);
  fireEvent.pointerMove(label, { clientX: 105, shiftKey: true });
  expect(onValueChange).toHaveBeenLastCalledWith(9);
  fireEvent.pointerMove(label, { clientX: 40 });
  expect(onValueChange).toHaveBeenLastCalledWith(3);
  fireEvent.pointerUp(label, { clientX: 40 });
  expect(onValueCommit).toHaveBeenCalledWith(3);
  // A press that does not move is a click: nothing written.
  onValueChange.mockClear(); onValueCommit.mockClear();
  fireEvent.pointerDown(label, { clientX: 100, button: 0 });
  fireEvent.pointerUp(label, { clientX: 101 });
  expect([onValueChange.mock.calls.length, onValueCommit.mock.calls.length]).toEqual([0, 0]);
});

it('neither types, steps nor scrubs while it is off', () => {
  const { container, input, box, onValueChange } = hole({ disabled: true });
  expect([input.disabled, box.hasAttribute('data-disabled')]).toEqual([true, true]);
  const label = container.querySelector('[data-slider-field-label]') as HTMLElement;
  expect(label.className).not.toContain('cursor-ew-resize');
  fireEvent.pointerDown(label, { clientX: 100, button: 0 });
  fireEvent.pointerMove(label, { clientX: 140 });
  expect(onValueChange).not.toHaveBeenCalled();
});

// The browser throws NotFoundError capturing, or releasing, a pointer it does not know (a synthetic press's
// id). The scrub works uncaptured then, and neither escapes the label's handlers as the page's crash.
it('scrubs from its label when the browser cannot capture the pointer', () => {
  const { container, onValueChange, onValueCommit } = hole();
  const label = container.querySelector('[data-slider-field-label]') as HTMLElement;
  const unknown = () => { throw new DOMException('No active pointer with the given id is found.', 'NotFoundError'); };
  Object.assign(label, { setPointerCapture: unknown, releasePointerCapture: unknown, hasPointerCapture: () => false });
  const errors: unknown[] = [];
  const record = (event: ErrorEvent) => { errors.push(event.error); event.preventDefault(); };
  window.addEventListener('error', record);
  try {
    fireEvent.pointerDown(label, { clientX: 100, button: 0 });
    fireEvent.pointerMove(label, { clientX: 105 });
    fireEvent.pointerUp(label, { clientX: 105 });
  } finally {
    window.removeEventListener('error', record);
  }
  expect(errors).toEqual([]);
  expect(onValueChange).toHaveBeenLastCalledWith(7.8);
  expect(onValueCommit).toHaveBeenCalledWith(7.8);
});
