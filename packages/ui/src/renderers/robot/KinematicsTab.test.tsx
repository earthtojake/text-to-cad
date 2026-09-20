import React from 'react';
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import KinematicsTab from '../../../dist/renderers/robot/KinematicsTab.js';
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

it('lists named poses, then a slider per joint a person can drive, then Reset', () => {
  render(<KinematicsTab pose={createPoseStore(description)}/>);
  expect(screen.getAllByRole('heading').map(heading => heading.textContent)).toEqual(['Pose', 'Joints']);
  expect([field('shoulder', 'deg').value, field('lift', 'm').value]).toEqual(['0°', '0 m']);
  expect(screen.queryByRole('textbox', { name: /mount|follower/ })).toBeNull();
  expect(screen.getByRole('button', { name: 'Reset' })).toBeTruthy();
});

it('a plain description has no Pose section, and one with nothing to move says so', () => {
  render(<KinematicsTab pose={createPoseStore({ joints: [joint('shoulder', 'revolute')] })}/>);
  expect(screen.getAllByRole('heading').map(heading => heading.textContent)).toEqual(['Joints']);
  cleanup();
  render(<KinematicsTab pose={createPoseStore({ joints: [joint('mount', 'fixed')] })}/>);
  expect(screen.getByText('No movable joints.')).toBeTruthy();
});

it('follows the pose store, and writes to it: a typed value is clamped, Reset returns the defaults', () => {
  const pose = createPoseStore(description);
  render(<KinematicsTab pose={pose}/>);
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
