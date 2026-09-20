import React from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import RobotComponentsSection from '../../../../../dist/renderers/cad/components/workbench/RobotComponentsSection.js';
import UrdfFileSheet from '../../../../../dist/renderers/cad/components/workbench/UrdfFileSheet.js';
import { HostPanelSlotContext } from '../../../../../dist/renderers/cad/components/workbench/FileSheet.js';
import { useRobotComponentSelection } from '../../../../../dist/renderers/cad/workbench/useRobotComponentSelection.js';

Object.assign(globalThis, { React });
afterEach(cleanup);

const joint = (name: string, type: string, parentLink: string, childLink: string, extra = {}) => ({ name, type, parentLink, childLink, axis: [0, 0, 1], ...extra });
const description = {
  robotName: 'arm', rootLink: 'base_footprint',
  links: [
    { name: 'base_footprint', visuals: [], collisions: [], inertial: null },
    { name: 'base_link', inertial: { mass: 2.5 }, collisions: [{ type: 'mesh', filename: 'meshes/base_collision.stl' }],
      visuals: [{ id: 'base_link:v1', filename: 'meshes/base.3mf', label: 'base.3mf', meshUrl: '/meshes/base.3mf' }] },
    { name: 'shoulder_link', visuals: [], collisions: [], inertial: { mass: 1.25 } },
    { name: 'elbow_link', visuals: [], collisions: [], inertial: null },
    { name: 'wrist_link', visuals: [], collisions: [], inertial: null },
    { name: 'camera_link', visuals: [], collisions: [], inertial: null },
  ],
  joints: [
    joint('footprint_to_base', 'fixed', 'base_footprint', 'base_link'),
    joint('shoulder_pan', 'revolute', 'base_link', 'shoulder_link', {
      origin: { xyz: [0, 0, 0.25], rpy: [0, 0, 1.5708] }, limit: { lower: -1.5708, upper: 1.5708, effort: 12, velocity: 3.5 },
    }),
    joint('elbow_lift', 'prismatic', 'shoulder_link', 'elbow_link', { limit: { lower: 0, upper: 0.2 } }),
    joint('wrist_roll', 'continuous', 'elbow_link', 'wrist_link'),
    joint('camera_mount', 'fixed', 'base_link', 'camera_link'),
  ],
};
const parts = [
  { id: 'base_link:v1', linkName: 'base_link' },
  { id: 'wrist_link:v1/object/0', linkName: 'wrist_link' }, { id: 'wrist_link:v1/object/1', linkName: 'wrist_link' },
];
const components = [
  { id: 'wrist_link:v1/object/0', name: 'flange', linkName: 'wrist_link', color: '#336699', triangleCount: 1200, vertexCount: 700, sizeMillimetres: [40, 40, 8] },
];
const geometry = { parts };

function Harness({ spy = {} as Record<string, (...args: any[]) => void>, groupNamesByLink = null as Map<string, string[]> | null }) {
  const selection = useRobotComponentSelection(components, geometry, 'arm.urdf');
  const observed = {
    ...selection,
    select: (...args: [string, any?]) => { spy.select?.(...args); selection.select(...args); },
    selectLink: (name: string) => { spy.selectLink?.(name); selection.selectLink(name); },
    hoverLink: (name: string) => { spy.hoverLink?.(name); selection.hoverLink(name); },
  };
  return <div>
    <RobotComponentsSection description={description} components={components} parts={parts} selection={observed} groupNamesByLink={groupNamesByLink}/>
    <output aria-label="Viewport selection">{JSON.stringify(selection.selectedIds)}</output>
    <output aria-label="Viewport hover">{JSON.stringify(selection.hoveredId)}</output>
  </div>;
}
const rows = () => within(screen.getByRole('list', { name: 'Robot links' })).getAllByRole('button', { name: /^Select / }).map(row => row.getAttribute('aria-label'));
const filter = () => screen.getByRole('textbox', { name: 'Filter components' });

it('draws the kinematic tree collapsed below the first real choice, with each link’s joint beside it', () => {
  render(<Harness/>);
  expect(filter().getAttribute('placeholder')).toBe('Filter components…');
  // base_footprint has a single child, so the chain opens until base_link offers a choice.
  expect(rows()).toEqual(['Select base_footprint', 'Select base_link', 'Select shoulder_link', 'Select camera_link']);
  const shoulder = screen.getByRole('button', { name: 'Select shoulder_link' });
  expect(shoulder.textContent).toBe('shoulder_linkshoulder_pan · revolute');
  expect(shoulder.closest('div')!.style.height).toBe('28px');
  expect(shoulder.getAttribute('title')).toBeNull();
  expect(screen.getByRole('button', { name: 'Select base_footprint' }).textContent).toBe('base_footprint');
  fireEvent.click(screen.getByRole('button', { name: 'Expand shoulder_link' }));
  expect(rows()).toContain('Select elbow_link');
  expect(rows()).not.toContain('Select wrist_link');
  fireEvent.click(screen.getByRole('button', { name: 'Collapse shoulder_link' }));
  expect(rows()).not.toContain('Select elbow_link');
  expect(screen.queryByRole('region', { name: 'Reference details' })).toBeNull();
});

it('selects a link as all of its viewport parts and reads the description back', () => {
  const spy = { selectLink: vi.fn(), hoverLink: vi.fn() };
  render(<Harness spy={spy} groupNamesByLink={new Map([['shoulder_link', ['manipulator']]])}/>);
  fireEvent.mouseEnter(screen.getByRole('button', { name: 'Select base_link' }).parentElement!);
  expect(spy.hoverLink).toHaveBeenLastCalledWith('base_link');
  expect(screen.getByLabelText('Viewport hover').textContent).toBe('["base_link:v1"]');
  fireEvent.click(screen.getByRole('button', { name: 'Select base_link' }));
  expect(spy.selectLink).toHaveBeenCalledWith('base_link');
  expect(screen.getByLabelText('Viewport selection').textContent).toBe('["base_link:v1"]');
  expect(screen.getByRole('button', { name: 'Select base_link' }).getAttribute('aria-pressed')).toBe('true');
  let details = within(screen.getByRole('region', { name: 'Reference details' }));
  expect(details.getByLabelText('Link details').textContent).toContain('2.5 kg');
  expect(details.getByLabelText('Link details').textContent).toContain('meshes/base.3mf');
  expect(details.getByLabelText('Link details').textContent).toContain('meshes/base_collision.stl');
  expect(details.getByLabelText('Parent joint').textContent).toContain('footprint_to_base');
  // A fixed joint has no axis or limits to report.
  expect(details.getByLabelText('Parent joint').textContent).not.toContain('Axis');
  expect(details.getByLabelText('Child joints').textContent).toContain('shoulder_link · shoulder_pan · revolute');

  // A link with no geometry is still a selection: the row, and what the description says.
  fireEvent.click(screen.getByRole('button', { name: 'Select shoulder_link' }));
  expect(screen.getByLabelText('Viewport selection').textContent).toBe('[]');
  details = within(screen.getByRole('region', { name: 'Reference details' }));
  const parentJoint = details.getByLabelText('Parent joint').textContent!;
  expect(parentJoint).toContain('shoulder_pan');
  expect(parentJoint).toContain('revolute');
  expect(parentJoint).toContain('-1.5708 … 1.5708 rad');
  expect(parentJoint).toContain('-90° … 90°');
  expect(parentJoint).toContain('12 N·m');
  expect(parentJoint).toContain('3.5 rad/s');
  expect(parentJoint).toContain('Z0.25');
  expect(details.getByLabelText('Link details').textContent).toContain('manipulator');
  expect(details.queryByRole('button', { name: /copy/i })).toBeNull();

  fireEvent.click(details.getByRole('button', { name: 'Clear selection' }));
  expect(screen.queryByRole('region', { name: 'Reference details' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Select shoulder_link' }).getAttribute('aria-pressed')).toBe('false');
});

it('filters to a flat ranked list by link, joint or object name without expanding anything', () => {
  render(<Harness/>);
  fireEvent.change(filter(), { target: { value: 'wrist' } });
  expect(screen.queryByRole('list', { name: 'Robot links' })).toBeNull();
  const results = within(screen.getByRole('list', { name: 'Component search results' }));
  expect(screen.getByText('1 match').getAttribute('role')).toBe('status');
  const hit = results.getByRole('button', { name: 'Select wrist_link' });
  // Name first, then the owners it sits under.
  expect(hit.textContent).toBe('wrist_linkbase_footprint/base_link/shoulder_link/elbow_link');

  // A joint name finds the link that hangs from it, and says why.
  fireEvent.change(filter(), { target: { value: 'elbow_lift' } });
  expect(within(screen.getByRole('list', { name: 'Component search results' })).getByRole('button', { name: 'Select elbow_link' }).textContent)
    .toBe('elbow_linkelbow_lift · prismatic');

  fireEvent.change(filter(), { target: { value: 'flange' } });
  expect(within(screen.getByRole('list', { name: 'Component search results' })).getByRole('button', { name: 'Select flange' })).toBeTruthy();

  fireEvent.change(filter(), { target: { value: 'nothing here' } });
  expect(screen.getByText('No link or component matches “nothing here”')).toBeTruthy();

  // Typing never touched the tree's expansion.
  fireEvent.click(screen.getByRole('button', { name: 'Clear filter' }));
  expect(rows()).toEqual(['Select base_footprint', 'Select base_link', 'Select shoulder_link', 'Select camera_link']);
});

it('reveals a selected hit with its ancestors expanded when the filter is cleared', () => {
  const scrollIntoView = vi.fn();
  Element.prototype.scrollIntoView = scrollIntoView;
  render(<Harness/>);
  fireEvent.change(filter(), { target: { value: 'wrist_roll' } });
  fireEvent.keyDown(filter(), { key: 'Enter' });
  expect(screen.getByLabelText('Viewport selection').textContent).toBe('["wrist_link:v1/object/0","wrist_link:v1/object/1"]');
  expect(within(screen.getByRole('region', { name: 'Reference details' })).getByLabelText('Parent joint').textContent).toContain('continuous');
  scrollIntoView.mockClear();
  fireEvent.keyDown(filter(), { key: 'Escape' });
  expect((filter() as HTMLInputElement).value).toBe('');
  // Its owners open; the hit itself stays closed.
  expect(rows()).toEqual(['Select base_footprint', 'Select base_link', 'Select shoulder_link', 'Select elbow_link', 'Select wrist_link', 'Select camera_link']);
  expect(screen.getByRole('button', { name: 'Select wrist_link' }).getAttribute('aria-pressed')).toBe('true');
  expect(scrollIntoView).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: 'Expand wrist_link' }));

  // A named object keeps its own selection and facts.
  fireEvent.click(screen.getByRole('button', { name: 'Select flange' }));
  expect(screen.getByLabelText('Viewport selection').textContent).toBe('["wrist_link:v1/object/0"]');
  const component = within(screen.getByRole('region', { name: 'Reference details' })).getByLabelText('Component details').textContent!;
  for (const fact of ['flange', 'wrist_link', '#336699', '1,200', '40.0 × 40.0 × 8.00 mm']) expect(component).toContain(fact);
});

it('a viewport pick of an unnamed part selects its link; a named object selects itself', () => {
  function Viewport() {
    const selection = useRobotComponentSelection(components, geometry, 'arm.urdf');
    return <div>
      <button type="button" onClick={() => selection.select('wrist_link:v1/object/1')}>Pick unnamed</button>
      <button type="button" onClick={() => selection.select('wrist_link:v1/object/0')}>Pick named</button>
      <RobotComponentsSection description={description} components={components} parts={parts} selection={selection}/>
    </div>;
  }
  render(<Viewport/>);
  fireEvent.click(screen.getByRole('button', { name: 'Pick unnamed' }));
  expect(screen.getByRole('button', { name: 'Select wrist_link' }).getAttribute('aria-pressed')).toBe('true');
  fireEvent.click(screen.getByRole('button', { name: 'Pick named' }));
  expect(screen.getByRole('button', { name: 'Select flange' }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('button', { name: 'Select wrist_link' }).getAttribute('aria-pressed')).toBe('false');
});

it('is the robot sheet’s second tab, after Motion and before View', () => {
  const selection = { selectedIds: [], selectedComponentIds: [], selectedLinkName: '', hoveredId: '', select() {}, selectLink() {}, hover() {}, hoverLink() {} };
  const slot = document.body.appendChild(document.createElement('div'));
  render(<HostPanelSlotContext.Provider value={slot}><UrdfFileSheet open isDesktop width={320} title="URDF" selectedEntry={{ file: 'arm.urdf' }} joints={[]} components={[]}
    robotDescription={description} robotParts={parts} componentSelection={selection}
    settingsTabs={[{ id: 'view', title: 'View', content: <p>View settings</p> }]}
    openSectionIds={['components']} onOpenSectionIdsChange={() => {}}/></HostPanelSlotContext.Provider>);
  expect(screen.getAllByRole('tab').map(tab => tab.textContent)).toEqual(['Motion', 'Components', 'View']);
  expect(screen.getByRole('tab', { name: 'Components' }).getAttribute('aria-selected')).toBe('true');
  expect(screen.getByRole('button', { name: 'Select base_link' })).toBeTruthy();
  slot.remove();
});
