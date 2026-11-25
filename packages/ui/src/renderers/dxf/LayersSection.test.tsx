import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, expect, it } from 'vitest';
import LayersSection from '../../../dist/renderers/dxf/LayersSection.js';

Object.assign(globalThis, { React });
afterEach(cleanup);

// A drawing of thousands of block references mounts the Layers' rows on screen, not one per reference:
// each is a row with its own tooltip, and the panel's search redraws the list on every key.
it('mounts a screenful of a drawing with thousands of block references', () => {
  const entities = new Map(Array.from({ length: 3000 }, (_, at) => {
    const handle = (0x100 + at).toString(16).toUpperCase();
    return [handle, { type: 'INSERT', handle, layer: 'HARDWARE', block: 'M5_NUT' }];
  }));
  const drawing = { entities, layers: [{ name: 'HARDWARE', color: '#ffffff', entities: 3000 }] };
  const selection = { selected: [], hover() {}, select() {} };
  const { container } = render(<LayersSection drawing={drawing} hiddenLayers={new Set()} onToggleLayer={() => {}} selection={selection} />);
  expect(container.querySelectorAll('[data-layer-row="HARDWARE"]')).toHaveLength(1);
  const mounted = container.querySelectorAll('[data-insert-row]').length;
  expect(mounted).toBeGreaterThan(0);
  expect(mounted).toBeLessThan(200);
});
