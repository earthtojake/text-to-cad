// One rule for every labelled control (`primitives/field-label.jsx`, Figma's): its label muted, its value the foreground.
import React from 'react';
import { cleanup, render } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { SliderField } from '../../../../dist/renderers/kit/inspector/SliderField.js';
import { FileSheetSettingRow } from '../../../../dist/renderers/kit/inspector/FileSheet.js';
import { KinematicsPoseRow } from '../../../../dist/renderers/kit/inspector/kinematicsControls.js';
import { ExplodeControls } from '../../../../dist/renderers/kit/tools/model-effects/ModelViewControls.js';
import { FieldLabel } from '../../../../dist/primitives/field-label.js';

beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const colours = (element: Element) => element.className.split(/\s+/).filter(name => /^(text-(foreground|muted-foreground|sidebar|primary|accent)|font-(medium|semibold|bold)|text-(tiny|micro|xs|ui))/.test(name));

it("every control's label is the one FieldLabel, muted at normal weight in its place's size, and its value the foreground: a slider's (Params', a joint's), a settings row's, Joints' Position, Explode's amount", () => {
  render(<div>
    <SliderField label="width" name="width" value={65} min={0} max={100} step={1} onValueChange={() => {}} text="65 mm" textLabel="width value" />
    <SliderField label="drive" name="drive" value={10} min={0} max={100} step={1} onValueChange={() => {}} text="10°" textLabel="drive value" />
    <FileSheetSettingRow label="Others"><span>Shown</span></FileSheetSettingRow>
    <KinematicsPoseRow poses={[{ value: 'open', label: 'Open' }]} activeValue="open" onSelect={() => {}} onReset={() => {}} />
    <ExplodeControls viewSettings={{ exploded: { enabled: true, amount: 0.4 } }} onViewSettingsPatch={() => {}} label={<FieldLabel>Explode</FieldLabel>} />
  </div>);
  const labels = [...document.querySelectorAll('[data-field-label]')];
  expect(labels.map(label => label.textContent)).toEqual(['width', 'drive', 'Others', 'Position', 'Explode']);
  // One colour and weight, no size of its own: every label's classes say the same.
  expect(new Set(labels.map(label => colours(label).join(' ')))).toEqual(new Set(['text-muted-foreground']));
  expect(labels.every(label => label.classList.contains('font-normal'))).toBe(true);
  // The values: the slider's fields and the pose chosen, the foreground.
  const values = [...document.querySelectorAll('[data-slider-field-value], [data-field-value]')];
  expect(values.length).toBe(4);
  for (const value of values) expect(colours(value)).toContain('text-foreground');
});
