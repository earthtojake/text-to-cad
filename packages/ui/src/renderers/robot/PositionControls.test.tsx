import React from 'react';
import { act, cleanup, fireEvent, render as mount, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import PositionControls from '../../../dist/renderers/robot/PositionControls.js';
import { createPoseStore } from '../../../dist/renderers/robot/poseStore.js';
import FlatPanel, { FLAT_PANEL_DEFAULT_WIDTH } from '../../../dist/renderers/kit/shell/FlatPanel.js';
import ToolPanel from '../../../dist/renderers/kit/tools/ToolPanel.js';
import { fixturePayload } from './__tests__/robotFixtures.js';

Object.assign(globalThis, { React });
// The slider primitive measures its thumb.
beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(cleanup);

// As the shell draws it: the Position tab of the view's panel, open.
const render = (controls: React.ReactElement) => mount(<FlatPanel mode="docked" open onClose={() => {}} label="Model panel" searchLabel="Search the model"
  sections={<ToolPanel id="position" title="Joints" label="Joint controls" fit="details">{controls}</ToolPanel>}
  tab="position" onTabChange={() => {}} width={FLAT_PANEL_DEFAULT_WIDTH} maxWidth={480} onWidthChange={() => {}} focusSearch={0} />);
const poseLabel = () => screen.getByRole('button', { name: /^Position: / }).getAttribute('aria-label');
const field = (name: string, unit: string) => screen.getByRole('textbox', { name: `${name} value in ${unit}` }) as HTMLInputElement;

it('opens on the pose row, full width over a slider per joint a person can drive, and Reset in the tab\'s actions row, last', () => {
  const pose = createPoseStore(fixturePayload('arm.urdf'));
  render(<PositionControls pose={pose}/>);
  // One tab's rows: the Position list around them is the panel's only one, under the panel's title (one tab is no pill), and no heading of its own.
  expect([screen.queryAllByRole('tab').length, screen.getByRole('tabpanel', { name: 'Joints' }) !== null, screen.getAllByRole('heading').map(heading => heading.textContent)]).toEqual([0, true, ['Joints']]);
  expect(poseLabel()).toBe('Position: Default');
  // The pose is the body's first row.
  expect(document.querySelector('[data-tool-panel-body] [data-pose-row] [data-pose-menu]')).not.toBeNull();
  // A slide in metres reads in millimetres.
  expect([field('shoulder', 'deg').value, field('lift', 'mm').value]).toEqual(['0', '0']);
  expect(screen.queryByRole('textbox', { name: /camera_mount|grip_mirror/ })).toBeNull();
  // Reset is the tab's actions row, after the joints, as Params' Reset is, idle at the default pose, and takes a moved joint back.
  const reset = screen.getByRole('button', { name: 'Reset joints' });
  const sliders = screen.getAllByRole('slider');
  expect([reset.closest('[data-pose-row]'), reset.closest('[data-pose-actions]') !== null, reset.textContent, (reset as HTMLButtonElement).disabled,
    Boolean(sliders.at(-1)!.compareDocumentPosition(reset) & Node.DOCUMENT_POSITION_FOLLOWING)]).toEqual([null, true, 'Reset', true, true]);
  act(() => { pose.write('shoulder', 30); });
  expect([poseLabel(), (reset as HTMLButtonElement).disabled]).toEqual(['Position: Custom', false]);
  fireEvent.click(reset);
  expect([pose.getSnapshot().values, poseLabel()]).toEqual([{ shoulder: 0, lift: 0, grip: 0, nod: 0 }, 'Position: Default']);
  // Each thumb is named for its joint, as its number field is.
  expect(screen.getAllByRole('slider').map(thumb => thumb.getAttribute('aria-label'))).toEqual(['shoulder', 'lift', 'grip', 'nod']);
});

it('a plain description offers the default pose, and one with nothing to move says so', () => {
  render(<PositionControls pose={createPoseStore(fixturePayload('arm.urdf'))}/>);
  expect(poseLabel()).toBe('Position: Default');
  expect(field('shoulder', 'deg').value).toBe('0');
  cleanup();
  const fixed = { articulation: { schemaVersion: 2, controls: [], joints: [{ id: 'mount', parent: null, kind: 'fixed' }], carries: { mount: ['camera'] }, handles: [], poses: {}, opening: {} } };
  render(<PositionControls pose={createPoseStore(fixed)}/>);
  expect(screen.getByText('No movable joints.')).toBeTruthy();
});

it('follows the pose store, and writes to it: a typed value is clamped, and a reset shows the defaults', () => {
  const pose = createPoseStore(fixturePayload('arm.srdf'));
  render(<PositionControls pose={pose}/>);
  act(() => { pose.write('shoulder', 30); });
  expect(field('shoulder', 'deg').value).toBe('30');
  // Typed in the field's millimetres, and clamped to the joint's limit.
  fireEvent.change(field('lift', 'mm'), { target: { value: '5000' } });
  fireEvent.blur(field('lift', 'mm'));
  expect(pose.getSnapshot().values.lift).toBe(0.3);
  act(() => { pose.selectGroupState(pose.groupStates.find(state => state.id === 'arm/raised')); });
  expect(poseLabel()).toBe('Position: raised');
  act(() => { pose.reset(); });
  const { shoulder, ...otherValues } = pose.getSnapshot().values;
  expect(shoulder).toBeCloseTo(-0.5 * 180 / Math.PI, 9);
  expect(otherValues).toEqual({ lift: 0.1, grip: 0, nod: 0 });
  expect(poseLabel()).toBe('Position: Default');
});

// The Joints tab's "changed" dot: on exactly while its Reset is (the pose off the default), from the same state.
it("the Joints tab's dot is on exactly while its Reset is", () => {
  const pose = createPoseStore(fixturePayload('arm.urdf'));
  render(<PositionControls pose={pose}/>);
  const heading = () => document.querySelector<HTMLElement>('[data-flat-panel-heading]')!;
  const state = () => [!(screen.getByRole('button', { name: 'Reset joints' }) as HTMLButtonElement).disabled, heading().hasAttribute('data-changed'),
    Boolean(heading().querySelector('[data-tool-changed]'))];
  expect(state()).toEqual([false, false, false]);
  act(() => { pose.write('shoulder', 30); });
  expect([...state(), heading().getAttribute('aria-label')]).toEqual([true, true, true, 'Joints, changed']);
  fireEvent.click(screen.getByRole('button', { name: 'Reset joints' }));
  expect(state()).toEqual([false, false, false]);
});
