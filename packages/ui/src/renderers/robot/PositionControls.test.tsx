import React from 'react';
import { act, cleanup, fireEvent, render as mount, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import PositionControls from '../../../dist/renderers/robot/PositionControls.js';
import { createPoseStore } from '../../../dist/renderers/robot/poseStore.js';
import FlatPanel from '../../../dist/renderers/kit/shell/FlatPanel.js';
import ToolPanel from '../../../dist/renderers/kit/tools/ToolPanel.js';
import { fixturePayload } from './__tests__/robotFixtures.js';

Object.assign(globalThis, { React });
// The slider primitive measures its thumb.
beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(cleanup);

// As the shell draws it: the Position tab of the view's panel, open.
const render = (controls: React.ReactElement) => mount(<FlatPanel mode="docked" open onClose={() => {}} label="Model panel" searchLabel="Search the model"
  searchPlaceholder="Search" sections={<ToolPanel id="position" title="Position" label="Position controls" fit="details">{controls}</ToolPanel>}
  tab="position" onTabChange={() => {}} width={240} maxWidth={480} onWidthChange={() => {}} focusSearch={0} />);
const poseLabel = () => screen.getByRole('button', { name: /^Pose: / }).getAttribute('aria-label');
const field = (name: string, unit: string) => screen.getByRole('textbox', { name: `${name} value in ${unit}` }) as HTMLInputElement;

it('opens on the pose row, full width over a slider per joint a person can drive, and Reset at the tab\'s top', () => {
  const pose = createPoseStore(fixturePayload('arm.urdf'));
  render(<PositionControls pose={pose}/>);
  // One tab's rows: the Position list around them is the panel's only one, so no row of tabs, and no heading of its own.
  expect([screen.queryAllByRole('tab').length, screen.getByRole('region', { name: 'Position controls' }) !== null, screen.queryAllByRole('heading').length]).toEqual([0, true, 0]);
  expect(poseLabel()).toBe('Pose: Default');
  // The pose is the body's first row, not the head's.
  expect([document.querySelector('[data-tool-panel-head-slot] [data-pose-menu]'), document.querySelector('[data-tool-panel-body] [data-pose-row] [data-pose-menu]') !== null]).toEqual([null, true]);
  // A slide in metres reads in millimetres.
  expect([field('shoulder', 'deg').value, field('lift', 'mm').value]).toEqual(['0°', '0 mm']);
  expect(screen.queryByRole('textbox', { name: /camera_mount|grip_mirror/ })).toBeNull();
  // Reset is the head's, idle at the default pose, and takes a moved joint back.
  const reset = screen.getByRole('button', { name: 'Reset position' });
  expect([reset.closest('[data-tool-panel-head-slot]') !== null, (reset as HTMLButtonElement).disabled]).toEqual([true, true]);
  act(() => { pose.write('shoulder', 30); });
  expect([poseLabel(), (reset as HTMLButtonElement).disabled]).toEqual(['Pose: Custom', false]);
  fireEvent.click(reset);
  expect([pose.getSnapshot().values, poseLabel()]).toEqual([{ shoulder: 0, lift: 0, grip: 0, nod: 0 }, 'Pose: Default']);
  // Each thumb is named for its joint, as its number field is.
  expect(screen.getAllByRole('slider').map(thumb => thumb.getAttribute('aria-label'))).toEqual(['shoulder', 'lift', 'grip', 'nod']);
});

it('a plain description offers the default pose, and one with nothing to move says so', () => {
  render(<PositionControls pose={createPoseStore(fixturePayload('arm.urdf'))}/>);
  expect(poseLabel()).toBe('Pose: Default');
  expect(field('shoulder', 'deg').value).toBe('0°');
  cleanup();
  const fixed = { articulation: { schemaVersion: 2, controls: [], joints: [{ id: 'mount', parent: null, kind: 'fixed' }], carries: { mount: ['camera'] }, handles: [], poses: {}, opening: {} } };
  render(<PositionControls pose={createPoseStore(fixed)}/>);
  expect(screen.getByText('No movable joints.')).toBeTruthy();
});

it('follows the pose store, and writes to it: a typed value is clamped, and a reset shows the defaults', () => {
  const pose = createPoseStore(fixturePayload('arm.srdf'));
  render(<PositionControls pose={pose}/>);
  act(() => { pose.write('shoulder', 30); });
  expect(field('shoulder', 'deg').value).toBe('30°');
  // Typed in the field's millimetres, and clamped to the joint's limit.
  fireEvent.change(field('lift', 'mm'), { target: { value: '5000' } });
  fireEvent.blur(field('lift', 'mm'));
  expect(pose.getSnapshot().values.lift).toBe(0.3);
  act(() => { pose.selectGroupState(pose.groupStates.find(state => state.id === 'arm/raised')); });
  expect(poseLabel()).toBe('Pose: raised');
  act(() => { pose.reset(); });
  const { shoulder, ...otherValues } = pose.getSnapshot().values;
  expect(shoulder).toBeCloseTo(-0.5 * 180 / Math.PI, 9);
  expect(otherValues).toEqual({ lift: 0.1, grip: 0, nod: 0 });
  expect(poseLabel()).toBe('Pose: Default');
});
