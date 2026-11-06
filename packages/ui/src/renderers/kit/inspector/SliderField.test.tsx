import React from 'react';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { SliderField } from '../../../../dist/renderers/kit/inspector/SliderField.js';

Object.assign(globalThis, { React });
// The slider primitive measures its thumb.
beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

// The one control for a number a slider sets: a label, an editable value with no box, a slider, and
// nothing before the label.
it('is a label, a quiet editable value and a slider, in that order, with no icon', () => {
  const onValueChange = vi.fn(), onTextCommit = vi.fn();
  const { container } = render(<SliderField label="Zones" name="Zone opacity" value={0.6} min={0} max={1} step={0.01}
    onValueChange={onValueChange} text="60%" onTextCommit={onTextCommit} textLabel="Zone opacity value" />);
  const root = container.querySelector('[data-slider-field]')!;
  const label = root.querySelector('[data-slider-field-label]')!;
  const value = screen.getByRole('textbox', { name: 'Zone opacity value' }) as HTMLInputElement;
  const thumb = screen.getByRole('slider', { name: 'Zone opacity' });
  expect([label.textContent, value.value, thumb.getAttribute('aria-valuenow')]).toEqual(['Zones', '60%', '0.6']);
  // Label, then value, on the first line; the slider after them.
  expect(label.compareDocumentPosition(value) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(value.compareDocumentPosition(thumb) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  expect(root.querySelector('svg')).toBeNull();
  // No box in any state: no border, ring or outline class on the value.
  const drawn = value.className.split(/\s+/).map(name => name.split(':').at(-1)!)
    .filter(name => /^(border|ring|outline|shadow)(-|$)/.test(name) && !/-(0|none|hidden)$/.test(name));
  expect(drawn).toEqual([]);
  // The value is typed and committed on Enter; the slider writes through `onValueChange`.
  fireEvent.focus(value);
  fireEvent.change(value, { target: { value: '25' } });
  fireEvent.keyDown(value, { key: 'Enter' });
  expect(onTextCommit).toHaveBeenCalledWith('25');
  fireEvent.keyDown(thumb, { key: 'ArrowRight' });
  expect(onValueChange).toHaveBeenCalledWith(0.61);
});
