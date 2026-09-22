import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import PositionControls from '../../../dist/renderers/robot/PositionControls.js';
import { createPoseStore } from '../../../dist/renderers/robot/poseStore.js';

Object.assign(globalThis, { React });
// The slider primitive measures its thumb.
beforeEach(() => vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} }));
afterEach(cleanup);

const joint = (name: string, type: string, extra = {}) => ({ name, type, parentLink: 'base', childLink: `${name}_link`, axis: [0, 0, 1], defaultValueDeg: 0, minValueDeg: -90, maxValueDeg: 90, ...extra });
const description = {
  joints: [joint('shoulder', 'revolute'), joint('lift', 'prismatic', { minValueDeg: 0, maxValueDeg: 0.3 }), joint('mount', 'fixed'),
    joint('follower', 'revolute', { mimic: { joint: 'shoulder', multiplier: 1, offset: 0 } })],
  srdf: { groupStates: [{ name: 'raised', group: 'arm', jointValuesByName: { shoulder: Math.PI / 4, lift: 0.2 } }] },
};
const field = (name: string, unit: string) => screen.getByRole('textbox', { name: `${name} value in ${unit}` }) as HTMLInputElement;

it('lists the named pose on a labelled row, then a slider per joint a person can drive, then Reset: no sections of its own', () => {
  render(<PositionControls pose={createPoseStore(description)}/>);
  // One section's rows: the Position section around them is the panel's.
  expect(screen.queryAllByRole('heading')).toEqual([]);
  expect(screen.getByRole('combobox', { name: 'Pose' }).textContent).toBe('None');
  expect(screen.getByText('Pose')).toBeTruthy();
  expect([field('shoulder', 'deg').value, field('lift', 'm').value]).toEqual(['0°', '0 m']);
  expect(screen.queryByRole('textbox', { name: /mount|follower/ })).toBeNull();
  expect(screen.getByRole('button', { name: 'Reset' })).toBeTruthy();
});

it('a plain description has no pose row, and one with nothing to move says so', () => {
  render(<PositionControls pose={createPoseStore({ joints: [joint('shoulder', 'revolute')] })}/>);
  expect(screen.queryByRole('combobox', { name: 'Pose' })).toBeNull();
  expect(field('shoulder', 'deg').value).toBe('0°');
  cleanup();
  render(<PositionControls pose={createPoseStore({ joints: [joint('mount', 'fixed')] })}/>);
  expect(screen.getByText('No movable joints.')).toBeTruthy();
});

it('follows the pose store, and writes to it: a typed value is clamped, Reset returns the defaults', () => {
  const pose = createPoseStore(description);
  render(<PositionControls pose={pose}/>);
  act(() => { pose.write(pose.joints[0], 30); });
  expect(field('shoulder', 'deg').value).toBe('30°');
  fireEvent.change(field('lift', 'm'), { target: { value: '5' } });
  fireEvent.blur(field('lift', 'm'));
  expect(pose.getSnapshot().values.lift).toBe(0.3);
  act(() => { pose.selectGroupState(pose.groupStates[0]); });
  expect(screen.getByRole('combobox').textContent).toBe('raised');
  fireEvent.click(screen.getByRole('button', { name: 'Reset' }));
  expect(pose.getSnapshot().values).toEqual({ shoulder: 0, lift: 0 });
  expect(screen.getByRole('combobox').textContent).toBe('None');
});
