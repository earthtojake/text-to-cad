import React from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import LinksSection from '../../../dist/renderers/robot/LinksSection.js';
import { useLinkSelection } from '../../../dist/renderers/robot/useLinkSelection.js';
import { useRobotReferences } from '../../../dist/renderers/robot/robotReferences.js';
import FileSidebar from '../../../dist/renderers/kit/tools/FileSidebar.js';

Object.assign(globalThis, { React });
afterEach(cleanup);

// A payload as cadgen resolves one (`cadgen.robot_payload`): links with their facts as written and the
// host path of each mesh file it could resolve, joints with `parent`/`child`, an SRDF's groups by link.
const joint = (name: string, type: string, parent: string, child: string, extra = {}) =>
  ({ name, type, parent, child, axis: type === 'fixed' ? null : [0, 0, 1], origin: null, limit: null, mimic: null, ...extra });
const origin = (xyz: number[], rpy = [0, 0, 0]) => ({ xyz, rpy });
const robot = {
  kind: 'urdf', name: 'arm', root: 'base_footprint',
  links: [
    { name: 'base_footprint', visuals: [], collisions: [], inertial: null },
    { name: 'base_link',
      inertial: { mass: 2.5, origin: origin([0, 0, 0.05]), inertia: { ixx: 0.01, ixy: 0, ixz: 0, iyy: 0.02, iyz: 0, izz: 0.03 } },
      collisions: [
        { name: '', type: 'mesh', filename: 'meshes/base_collision.stl', path: 'robots/arm/meshes/base_collision.stl', origin: origin([0, 0, 0]) },
        { name: '', type: 'box', filename: '', size: [0.1, 0.2, 0.3], origin: origin([0, 0, 0.5]) },
        // A reference cadgen could not resolve to a file (a package:// URI) has no path.
        { name: '', type: 'mesh', filename: 'package://arm/meshes/far.stl', origin: origin([0, 0, 0]) },
      ],
      visuals: [{ name: '', type: 'mesh', filename: 'meshes/base.3mf', path: 'robots/arm/meshes/base.3mf', scale: [0.001, 0.001, 0.001], origin: origin([0, 0, 0]), color: '#336699', materialName: 'blue' }] },
    { name: 'shoulder_link', visuals: [], collisions: [], inertial: { mass: 1.25 } },
    { name: 'elbow_link', visuals: [], collisions: [], inertial: null },
    { name: 'wrist_link', visuals: [], collisions: [], inertial: null },
    { name: 'camera_link', visuals: [], collisions: [], inertial: null },
  ],
  joints: [
    joint('footprint_to_base', 'fixed', 'base_footprint', 'base_link'),
    joint('shoulder_pan', 'revolute', 'base_link', 'shoulder_link', {
      origin: origin([0, 0, 0.25], [0, 0, 1.5708]), limit: { lower: -1.5708, upper: 1.5708, effort: 12, velocity: 3.5 },
    }),
    joint('elbow_lift', 'prismatic', 'shoulder_link', 'elbow_link', { limit: { lower: 0, upper: 0.2 } }),
    joint('wrist_roll', 'continuous', 'elbow_link', 'wrist_link'),
    joint('camera_mount', 'fixed', 'base_link', 'camera_link'),
  ],
  srdf: null,
};
const planned = { ...robot, srdf: { planningGroups: [], endEffectors: [], groupStates: [], disabledCollisionPairs: [], groupsByLink: { shoulder_link: ['manipulator'] } } };
const parts = [
  { id: 'base_link:v1', link: 'base_link' },
  { id: 'wrist_link:v1/object/0', link: 'wrist_link' }, { id: 'wrist_link:v1/object/1', link: 'wrist_link' },
];
const components = [
  { id: 'wrist_link:v1/object/0', name: 'flange', link: 'wrist_link', color: '#336699', triangleCount: 1200, vertexCount: 700, sizeMillimetres: [40, 40, 8] },
  { id: 'wrist_link:v1/object/1', name: 'cap', link: 'wrist_link', color: '', triangleCount: 300, vertexCount: 150, sizeMillimetres: [40, 40, 2] },
];

const meshPath = (filename: string) => (filename.includes(':') ? '' : `robots/arm/${filename}`);
const groupNamesByLink = new Map([['shoulder_link', ['manipulator']]]);

// What the scene graph was last asked to draw: the viewport half of a selection. What is selected
// reads back as Quick Edit's chips (`robotReferences.jsx`); the harness lays each chip's card out
// flat under "Reference details", with its X, as its popover would show it.
let highlight: Record<string, unknown> = {};
const scene = { hasComponent: (id: string) => components.some(component => component.id === id), setHighlight(next: Record<string, unknown>) { highlight = next; } };
const drawn = () => JSON.stringify([highlight.selectedLinks || [], highlight.selectedComponents || []]);
function Harness({ spy = {} as Record<string, (...args: any[]) => void>, payload = robot as typeof planned, onOpenFile = undefined as ((path: string) => void) | undefined,
  hiddenPartIds = undefined as string[] | undefined, onVisibilityChange = undefined as ((ids: string[], visible: boolean) => void) | undefined }) {
  const selection = useLinkSelection({ scene, hidden: false, requestRender() {} });
  const observed = {
    ...selection,
    select: (...args: [string, any?]) => { spy.select?.(...args); selection.select(...args); },
    selectLink: (name: string, options?: any) => { spy.selectLink?.(name); selection.selectLink(name, options); },
    hoverLink: (name: string) => { spy.hoverLink?.(name); selection.hoverLink(name); },
  };
  const { references, chips } = useRobotReferences({ robot: payload, components, selection: observed, groupNamesByLink, meshPath, resource: { kind: 'workspace-file', path: '/work/arm.urdf' }, onOpenFile });
  return <>
    {/* In the file sidebar, as it ships: a section its Links tile opens, headed by its search box. */}
    <FileSidebar layout={{ panels: {}, collapsed: {} }} onLayoutChange={() => {}}>
      <LinksSection robot={payload} components={components} parts={parts} selection={observed} hiddenPartIds={hiddenPartIds} onVisibilityChange={onVisibilityChange}/>
    </FileSidebar>
    {chips.length ? <section aria-label="Reference details" data-references={JSON.stringify(references.map((reference: any) => reference.target.selectors))}>
      {chips.map((chip: any) => <div key={chip.key} aria-label={`Chip ${chip.label}`} data-copy={chip.copy}>
        {chip.card}<button type="button" onClick={chip.onRemove}>Remove {chip.label}</button>
      </div>)}
    </section> : null}
  </>;
}
const chipLabels = () => within(screen.getByRole('region', { name: 'Reference details' })).getAllByRole('generic', { name: /^Chip / })
  .map(chip => chip.getAttribute('aria-label'));
const rows = () => within(screen.getByRole('list', { name: 'Robot links' })).getAllByRole('button', { name: /^Select / }).map(row => row.getAttribute('aria-label'));
const filter = () => screen.getByRole('textbox', { name: 'Filter links' });

it('draws the kinematic tree collapsed below the first real choice, with each link’s joint beside it', () => {
  render(<Harness/>);
  // Its tile is named for the section and opens it; its head is the search box, no heading, and the X that closes it.
  const tile = within(screen.getByRole('group', { name: 'File sidebar' })).getByRole('button', { name: 'Links' });
  fireEvent.click(tile);
  expect(tile.getAttribute('aria-pressed')).toBe('true');
  const head = document.querySelector<HTMLElement>('[data-sidebar-head]')!;
  expect([head.contains(filter()), filter().getAttribute('placeholder'), head.querySelector('[data-tool-panel-heading]')]).toEqual([true, 'Filter…', null]);
  fireEvent.click(within(head).getByRole('button', { name: 'Close links' }));
  expect(tile.getAttribute('aria-pressed')).toBe('false');
  // base_footprint is only a frame (no geometry, no mass, base_link fixed to it): it has nothing
  // to select or read back, so it gets no row and base_link leads the tree.
  expect(rows()).toEqual(['Select base_link', 'Select shoulder_link', 'Select camera_link']);
  const shoulder = screen.getByRole('button', { name: 'Select shoulder_link' });
  expect(shoulder.textContent).toBe('shoulder_linkshoulder_pan · revolute');
  expect(shoulder.closest('div')!.style.height).toBe('24px'); // the dense tree's rows
  expect(shoulder.getAttribute('title')).toBeNull();
  expect(screen.getByRole('button', { name: 'Select base_link' }).textContent).toBe('base_linkfootprint_to_base · fixed');
  // The one root is pinned: a row you can select, with nothing to collapse and no indent
  // level of its own, so its child starts at the tree's left edge. Links carry no icons (a mesh
  // object's row carries the part box, below).
  expect(screen.queryByRole('button', { name: /^(Collapse|Expand) base_link$/ })).toBeNull();
  const indent = (name: string) => (screen.getByRole('button', { name: `Select ${name}` }).closest('div') as HTMLElement).style.paddingLeft;
  expect([indent('base_link'), indent('shoulder_link'), indent('camera_link')]).toEqual(['0px', '0px', '0px']);
  expect(screen.getByRole('list', { name: 'Robot links' }).querySelectorAll('svg.lucide-box, svg.lucide-boxes')).toHaveLength(0);
  fireEvent.click(screen.getByRole('button', { name: 'Expand shoulder_link' }));
  expect(rows()).toContain('Select elbow_link');
  expect(rows()).not.toContain('Select wrist_link');
  fireEvent.click(screen.getByRole('button', { name: 'Collapse shoulder_link' }));
  expect(rows()).not.toContain('Select elbow_link');
  expect(screen.queryByRole('region', { name: 'Reference details' })).toBeNull();
});

it('selects a link in the scene graph and reads the payload back', () => {
  const spy = { selectLink: vi.fn(), hoverLink: vi.fn() };
  render(<Harness spy={spy} payload={planned}/>);
  fireEvent.mouseEnter(screen.getByRole('button', { name: 'Select base_link' }).parentElement!);
  expect(spy.hoverLink).toHaveBeenLastCalledWith('base_link');
  expect(highlight.hoveredLink).toBe('base_link');
  fireEvent.click(screen.getByRole('button', { name: 'Select base_link' }));
  expect(spy.selectLink).toHaveBeenCalledWith('base_link');
  expect(drawn()).toBe('[["base_link"],[]]');
  expect(screen.getByRole('button', { name: 'Select base_link' }).getAttribute('aria-pressed')).toBe('true');
  let details = within(screen.getByRole('region', { name: 'Reference details' }));
  expect(details.getByLabelText('Link details').textContent).toContain('2.5 kg');
  expect(details.getByLabelText('Link details').textContent).toContain('meshes/base.3mf');
  expect(details.getByLabelText('Link details').textContent).toContain('meshes/base_collision.stl');
  expect(details.getByLabelText('Parent joint').textContent).toContain('footprint_to_base');
  // A fixed joint has no axis or limits to report.
  expect(details.getByLabelText('Parent joint').textContent).not.toContain('Axis');
  expect(details.getByLabelText('Child joints').textContent).toContain('shoulder_link · shoulder_pan · revolute');

  // A link with no geometry is still a selection: the row, and what the payload says.
  fireEvent.click(screen.getByRole('button', { name: 'Select shoulder_link' }));
  expect(drawn()).toBe('[["shoulder_link"],[]]');
  details = within(screen.getByRole('region', { name: 'Reference details' }));
  const parentJoint = details.getByLabelText('Parent joint').textContent!;
  expect(parentJoint).toContain('shoulder_pan');
  expect(parentJoint).toContain('revolute');
  expect(parentJoint).toContain('-1.5708 … 1.5708 rad');
  expect(parentJoint).toContain('-90° … 90°');
  expect(parentJoint).toContain('12 N·m');
  expect(parentJoint).toContain('3.5 rad/s');
  expect(parentJoint).toContain('Z0.25');
  // The SRDF's planning group the link is in.
  expect(details.getByLabelText('Link details').textContent).toContain('manipulator');
  // Its chip copies its reference into the description: the file, and the link by name.
  expect(details.getByLabelText('Chip shoulder_link').getAttribute('data-copy')).toBe('/work/arm.urdf#shoulder_link');

  fireEvent.click(details.getByRole('button', { name: 'Remove shoulder_link' }));
  expect(screen.queryByRole('region', { name: 'Reference details' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Select shoulder_link' }).getAttribute('aria-pressed')).toBe('false');
});

it('names a mesh as plain text where the view opens no other file (a host’s file handler)', () => {
  render(<Harness/>);
  fireEvent.click(screen.getByRole('button', { name: 'Select base_link' }));
  const details = within(screen.getByRole('region', { name: 'Reference details' }));
  expect(details.getByText('meshes/base.3mf').closest('button')).toBeNull();
});

it('reads a link’s inertial and geometry back, opens the mesh files it names by cadgen’s path and follows its parent and children', () => {
  const onOpenFile = vi.fn();
  render(<Harness onOpenFile={onOpenFile}/>);
  fireEvent.click(screen.getByRole('button', { name: 'Select base_link' }));
  let details = within(screen.getByRole('region', { name: 'Reference details' }));
  const inertial = details.getByLabelText('Inertial').textContent!;
  expect(inertial).toContain('2.5 kg');
  expect(inertial).toContain('Z0.05');
  for (const term of ['0.01', '0.02', '0.03']) expect(inertial).toContain(term);
  // Nine cells the panel's width: a long value truncates in its cell (its hint has the whole),
  // never wrapping inside the number.
  const cells = details.getByLabelText('Inertial').querySelectorAll('[data-inertia-term]');
  expect(cells).toHaveLength(9);
  for (const cell of cells) expect(cell.className.split(' ')).toEqual(expect.arrayContaining(['min-w-0', 'truncate']));
  // Only what the description bothered to say: a scale that is not 1, an origin that is not zero.
  const geometry = details.getByLabelText('Geometry').textContent!;
  expect(geometry).toContain('scale 0.001  0.001  0.001');
  expect(geometry).toContain('0.1 × 0.2 × 0.3 m');
  expect(geometry).toContain('xyz 0  0  0.5');
  expect(geometry).not.toContain('rpy');

  fireEvent.click(details.getByRole('button', { name: 'meshes/base.3mf' }));
  fireEvent.click(details.getByRole('button', { name: 'meshes/base_collision.stl' }));
  expect(onOpenFile.mock.calls).toEqual([['robots/arm/meshes/base.3mf'], ['robots/arm/meshes/base_collision.stl']]);
  // A reference with no path is text, not a link that leads nowhere.
  expect(details.getByText('package://arm/meshes/far.stl').closest('button')).toBeNull();

  // Parent and children are the same tree: pressing one selects it there and in the viewport.
  fireEvent.click(within(details.getByLabelText('Child joints')).getByRole('button', { name: 'shoulder_link' }));
  expect(screen.getByRole('button', { name: 'Select shoulder_link' }).getAttribute('aria-pressed')).toBe('true');
  details = within(screen.getByRole('region', { name: 'Reference details' }));
  fireEvent.click(within(details.getByLabelText('Parent joint')).getByRole('button', { name: 'base_link' }));
  expect(screen.getByRole('button', { name: 'Select base_link' }).getAttribute('aria-pressed')).toBe('true');
  expect(drawn()).toBe('[["base_link"],[]]');
});

it('filters to a flat ranked list by link, joint or object name without expanding anything', () => {
  render(<Harness/>);
  fireEvent.change(filter(), { target: { value: 'wrist' } });
  expect(screen.queryByRole('list', { name: 'Robot links' })).toBeNull();
  const results = within(screen.getByRole('list', { name: 'Link search results' }));
  expect(screen.getByText('1 match').getAttribute('role')).toBe('status');
  const hit = results.getByRole('button', { name: 'Select wrist_link' });
  // Name first, then the owners it sits under.
  expect(hit.textContent).toBe('wrist_linkbase_link/shoulder_link/elbow_link');

  // A joint name finds the link that hangs from it, and says why.
  fireEvent.change(filter(), { target: { value: 'elbow_lift' } });
  expect(within(screen.getByRole('list', { name: 'Link search results' })).getByRole('button', { name: 'Select elbow_link' }).textContent)
    .toBe('elbow_linkelbow_lift · prismatic');

  fireEvent.change(filter(), { target: { value: 'flange' } });
  expect(within(screen.getByRole('list', { name: 'Link search results' })).getByRole('button', { name: 'Select flange' })).toBeTruthy();

  fireEvent.change(filter(), { target: { value: 'nothing here' } });
  expect(screen.getByText('No link matches “nothing here”')).toBeTruthy();

  // Typing never touched the tree's expansion.
  fireEvent.click(screen.getByRole('button', { name: 'Clear filter' }));
  expect(rows()).toEqual(['Select base_link', 'Select shoulder_link', 'Select camera_link']);
});

it('reveals a selected hit with its ancestors expanded when the filter is cleared', () => {
  const scrollIntoView = vi.fn();
  Element.prototype.scrollIntoView = scrollIntoView;
  render(<Harness/>);
  fireEvent.change(filter(), { target: { value: 'wrist_roll' } });
  fireEvent.keyDown(filter(), { key: 'Enter' });
  expect(drawn()).toBe('[["wrist_link"],[]]');
  expect(within(screen.getByRole('region', { name: 'Reference details' })).getByLabelText('Parent joint').textContent).toContain('continuous');
  scrollIntoView.mockClear();
  fireEvent.keyDown(filter(), { key: 'Escape' });
  expect((filter() as HTMLInputElement).value).toBe('');
  // Its owners open; the hit itself stays closed.
  expect(rows()).toEqual(['Select base_link', 'Select shoulder_link', 'Select elbow_link', 'Select wrist_link', 'Select camera_link']);
  expect(screen.getByRole('button', { name: 'Select wrist_link' }).getAttribute('aria-pressed')).toBe('true');
  expect(scrollIntoView).toHaveBeenCalledTimes(1);
  fireEvent.click(screen.getByRole('button', { name: 'Expand wrist_link' }));

  // A named object keeps its own selection and facts, and its row the part box.
  expect(screen.getByRole('button', { name: 'Select flange' }).closest('div')!.querySelector('svg.lucide-box')).not.toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Select flange' }));
  expect(drawn()).toBe('[[],["wrist_link:v1/object/0"]]');
  const reference = within(screen.getByRole('region', { name: 'Reference details' }));
  // The chip names it; the card's rows say the rest, never the name again. It is a reference to its link.
  expect(chipLabels()).toEqual(['Chip flange']);
  expect(reference.getByLabelText('Chip flange').getAttribute('data-copy')).toBe('/work/arm.urdf#wrist_link');
  const component = reference.getByLabelText('Component details').textContent!;
  for (const fact of ['wrist_link', '#336699', '1,200', '40.0 × 40.0 × 8.00 mm']) expect(component).toContain(fact);
  expect(component).not.toContain('flange');
});

it('a viewport pick of a surface selects its link; a named object selects itself, and Shift adds', () => {
  function Viewport() {
    const selection = useLinkSelection({ scene, hidden: false, requestRender() {} });
    return <div>
      <button type="button" onClick={() => selection.pick({ linkName: 'wrist_link', componentId: '' })}>Pick surface</button>
      <button type="button" onClick={() => selection.pick({ linkName: 'wrist_link', componentId: 'wrist_link:v1/object/0' }, { multiSelect: true })}>Pick named</button>
      <button type="button" onClick={() => selection.pick(null)}>Pick nothing</button>
      <LinksSection robot={robot} components={components} parts={parts} selection={selection}/>
    </div>;
  }
  render(<Viewport/>);
  fireEvent.click(screen.getByRole('button', { name: 'Pick surface' }));
  expect(screen.getByRole('button', { name: 'Select wrist_link' }).getAttribute('aria-pressed')).toBe('true');
  fireEvent.click(screen.getByRole('button', { name: 'Pick named' }));
  expect(screen.getByRole('button', { name: 'Select flange' }).getAttribute('aria-pressed')).toBe('true');
  expect(screen.getByRole('button', { name: 'Select wrist_link' }).getAttribute('aria-pressed')).toBe('false');
  // Shift on the one selected object takes it back out.
  fireEvent.click(screen.getByRole('button', { name: 'Pick named' }));
  expect(screen.getByRole('button', { name: 'Select flange' }).getAttribute('aria-pressed')).toBe('false');
  fireEvent.click(screen.getByRole('button', { name: 'Pick surface' }));
  fireEvent.click(screen.getByRole('button', { name: 'Pick nothing' }));
  expect(screen.queryByRole('region', { name: 'Reference details' })).toBeNull();
});

it('a row that draws something has the Hide/Reveal eye: a link hides its own visuals, a partly hidden link the rest, and several visuals are a chip each', () => {
  const onVisibilityChange = vi.fn();
  const { rerender } = render(<Harness onVisibilityChange={onVisibilityChange} hiddenPartIds={[]}/>);
  // A link with no geometry of its own (shoulder_link) has no eye; base_link draws one visual.
  expect(screen.queryByRole('button', { name: /^(Hide|Reveal) shoulder_link$/ })).toBeNull();
  fireEvent.click(screen.getByRole('button', { name: 'Hide base_link' }));
  expect(onVisibilityChange).toHaveBeenLastCalledWith(['base_link:v1'], false);
  // The eye is its own press: the row is not selected by it.
  expect(screen.getByRole('button', { name: 'Select base_link' }).getAttribute('aria-pressed')).toBe('false');
  // wrist_link's two objects: with one hidden the link is partly hidden, so its eye hides the rest.
  fireEvent.click(screen.getByRole('button', { name: 'Expand shoulder_link' }));
  fireEvent.click(screen.getByRole('button', { name: 'Expand elbow_link' }));
  rerender(<Harness onVisibilityChange={onVisibilityChange} hiddenPartIds={['wrist_link:v1/object/0']}/>);
  fireEvent.click(screen.getByRole('button', { name: 'Hide wrist_link' }));
  expect(onVisibilityChange).toHaveBeenLastCalledWith(['wrist_link:v1/object/0', 'wrist_link:v1/object/1'], false);
  rerender(<Harness onVisibilityChange={onVisibilityChange} hiddenPartIds={['wrist_link:v1/object/0', 'wrist_link:v1/object/1']}/>);
  fireEvent.click(screen.getByRole('button', { name: 'Reveal wrist_link' }));
  expect(onVisibilityChange).toHaveBeenLastCalledWith(['wrist_link:v1/object/0', 'wrist_link:v1/object/1'], true);
  // A search hit carries the eye too, and a visual's eye is its own.
  fireEvent.change(filter(), { target: { value: 'flange' } });
  fireEvent.click(within(screen.getByRole('list', { name: 'Link search results' })).getByRole('button', { name: 'Reveal flange' }));
  expect(onVisibilityChange).toHaveBeenLastCalledWith(['wrist_link:v1/object/0'], true);
  fireEvent.click(screen.getByRole('button', { name: 'Clear filter' }));
  // Two visuals selected: a chip each, and one reference, to the link they share.
  fireEvent.click(screen.getByRole('button', { name: 'Expand wrist_link' }));
  fireEvent.click(screen.getByRole('button', { name: 'Select flange' }));
  fireEvent.click(screen.getByRole('button', { name: 'Select cap' }), { shiftKey: true });
  expect(chipLabels()).toEqual(['Chip flange', 'Chip cap']);
  expect(screen.getByRole('region', { name: 'Reference details' }).getAttribute('data-references')).toBe('[["wrist_link"]]');
  // Without a handler there is no eye at all.
  rerender(<Harness/>);
  expect(within(screen.getByRole('list', { name: 'Robot links' })).queryByRole('button', { name: /^(Hide|Reveal) / })).toBeNull();
});

it('a modified click adds a link to the selection, as it adds an object, and a plain one goes back to one', () => {
  render(<Harness/>);
  fireEvent.click(screen.getByRole('button', { name: 'Select base_link' }));
  fireEvent.click(screen.getByRole('button', { name: 'Select shoulder_link' }), { shiftKey: true });
  expect(drawn()).toBe('[["base_link","shoulder_link"],[]]');
  expect(screen.getAllByRole('button', { pressed: true }).map(row => row.getAttribute('aria-label')))
    .toEqual(['Select base_link', 'Select shoulder_link']);
  // Several links are a chip each, and a reference each.
  expect(chipLabels()).toEqual(['Chip base_link', 'Chip shoulder_link']);
  expect(screen.getByRole('region', { name: 'Reference details' }).getAttribute('data-references')).toBe('[["base_link"],["shoulder_link"]]');
  fireEvent.click(screen.getByRole('button', { name: 'Select base_link' }), { metaKey: true });
  expect(drawn()).toBe('[["shoulder_link"],[]]');
  fireEvent.click(screen.getByRole('button', { name: 'Select base_link' }));
  expect(drawn()).toBe('[["base_link"],[]]');
});
