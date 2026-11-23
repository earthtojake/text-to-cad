import React from 'react';
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import LinksSection from '../../../dist/renderers/robot/LinksSection.js';
import { useLinkSelection } from '../../../dist/renderers/robot/useLinkSelection.js';
import { useRobotDescribe, useRobotInspect, useRobotReferences, useRobotTip } from '../../../dist/renderers/robot/robotReferences.js';
import ItemDetail from '../../../dist/renderers/kit/inspector/ItemDetail.js';
import { robotLinkItem } from '../../../dist/renderers/robot/LinkDetails.js';
import { robotLinkFacts } from '../../../dist/renderers/robot/robotTree.js';
import { InspectContext } from '../../../dist/renderers/kit/inspector/inspect.js';
import FlatPanel, { FLAT_PANEL_DEFAULT_WIDTH } from '../../../dist/renderers/kit/shell/FlatPanel.js';
import ToolPanel from '../../../dist/renderers/kit/tools/ToolPanel.js';

Object.assign(globalThis, { React });
afterEach(cleanup);

// A payload as the server resolves one (`cad_server.robot_payload`): links with their facts as written and the
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
        // A reference the server could not resolve to a file (a package:// URI) has no path.
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

// What the scene graph was last asked to draw: the viewport half of a selection. What is selected
// reads back as Quick Edit's chips (`robotReferences.jsx`); the harness lays each chip's card out
// flat under "Reference details" (`ItemDetail`, as its popover draws it), with its X.
let highlight: Record<string, unknown> = {};
const scene = { hasComponent: (id: string) => components.some(component => component.id === id), setHighlight(next: Record<string, unknown>) { highlight = next; } };
const drawn = () => JSON.stringify([highlight.selectedLinks || [], highlight.selectedComponents || []]);
function Harness({ spy = {} as Record<string, (...args: any[]) => void>, payload = robot as typeof planned,
  hiddenPartIds = undefined as string[] | undefined, onVisibilityChange = undefined as ((ids: string[], visible: boolean) => void) | undefined }) {
  const selection = useLinkSelection({ scene, hidden: false, requestRender() {} });
  const observed = {
    ...selection,
    select: (...args: [string, any?]) => { spy.select?.(...args); selection.select(...args); },
    selectLink: (name: string, options?: any) => { spy.selectLink?.(name); selection.selectLink(name, options); },
    hoverLink: (name: string) => { spy.hoverLink?.(name); selection.hoverLink(name); },
  };
  const resource = { kind: 'workspace-file', path: '/work/arm.urdf' };
  const describe = useRobotDescribe({ robot: payload, components, selectLink: observed.selectLink });
  const { references, chips } = useRobotReferences({ robot: payload, components, selection: observed, resource, describe });
  const inspect = useRobotInspect({ selection: observed, describe });
  return <InspectContext.Provider value={inspect}>
    {/* In the view's panel, as it ships: its Links tab, searched by the panel's search box. */}
    <FlatPanel mode="docked" open onClose={() => {}} label="Model panel" searchLabel="Search the model"
      sections={<LinksSection robot={payload} components={components} parts={parts} selection={observed} hiddenPartIds={hiddenPartIds} onVisibilityChange={onVisibilityChange}/>}
      tab="tree" onTabChange={() => {}} width={FLAT_PANEL_DEFAULT_WIDTH} maxWidth={480} onWidthChange={() => {}} focusSearch={0} />
    {chips.length ? <section aria-label="Reference details" data-references={JSON.stringify(references.map((reference: any) => reference.target.selectors))}>
      {chips.map((chip: any) => <div key={chip.key} aria-label={`Chip ${chip.label}`} data-copy={chip.copy}>
        {chip.detail ? <ItemDetail item={chip.detail} copy={chip.copy} /> : null}<button type="button" onClick={chip.onRemove}>Remove {chip.label}</button>
      </div>)}
    </section> : null}
  </InspectContext.Provider>;
}
const chipLabels = () => within(screen.getByRole('region', { name: 'Reference details' })).getAllByRole('generic', { name: /^Chip / })
  .map(chip => chip.getAttribute('aria-label'));
const rows = () => within(screen.getByRole('list', { name: 'Robot links' })).getAllByRole('button', { name: /^Select / }).map(row => row.getAttribute('aria-label'));
// The panel's search box, the Links tab's first row.
// The panel's search, opened from its icon at the head row's right end where it is shut.
const filter = () => {
  if (!screen.queryByRole('textbox', { name: 'Search the model' })) fireEvent.click(screen.getByRole('button', { name: 'Search the model' }));
  return screen.getByRole('textbox', { name: 'Search the model' }) as HTMLInputElement;
};

it('draws the kinematic tree collapsed below the first real choice, with each link’s joint beside it', () => {
  render(<Harness/>);
  // The panel's one list, under its one tab's title: it is named for the section; the panel's search box searches it, and it draws no heading of its own.
  expect([screen.queryAllByRole('tab').length, screen.getByRole('tabpanel', { name: 'Links' }) !== null, screen.getByRole('heading', { name: 'Links' }) !== null]).toEqual([0, true, true]);
  const tab = document.querySelector<HTMLElement>('[data-flat-panel-section="tree"]')!;
  expect([tab.contains(filter()), filter().getAttribute('placeholder'), tab.querySelector('[data-tool-panel-heading], h3')]).toEqual([false, 'Search', null]);
  // base_footprint is only a frame (no geometry, no mass, base_link fixed to it): it has nothing
  // to select or read back, so it gets no row and base_link leads the tree.
  expect(rows()).toEqual(['Select base_link', 'Select shoulder_link', 'Select camera_link']);
  const shoulder = screen.getByRole('button', { name: 'Select shoulder_link' });
  expect(shoulder.textContent).toBe('shoulder_linkshoulder_pan · revolute');
  expect(shoulder.closest('div')!.style.height).toBe('var(--cad-row)'); // the panel's rows (the scale's row)
  expect(shoulder.getAttribute('title')).toBeNull();
  expect(screen.getByRole('button', { name: 'Select base_link' }).textContent).toBe('base_linkfootprint_to_base · fixed');
  // The one root is pinned: a row you can select, with nothing to collapse and no indent
  // level of its own, so its child starts at the tree's left edge. Links carry no icons (a mesh
  // object's row carries the part box, below).
  expect(screen.queryByRole('button', { name: /^(Collapse|Expand) base_link$/ })).toBeNull();
  const indent = (name: string) => (screen.getByRole('button', { name: `Select ${name}` }).closest('div') as HTMLElement).style.paddingLeft;
  expect(new Set([indent('base_link'), indent('shoulder_link'), indent('camera_link')]).size).toBe(1);
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
  // The card is the link alone: its mass and the joint that holds it, never its geometry or its children.
  const facts = (name: string) => [...details.getByRole('region', { name }).querySelectorAll('[data-info-row]')]
    .map(row => [row.querySelector('dt')!.textContent, row.querySelector('dd')!.textContent]);
  expect(facts('base_link')).toEqual([['Mass', '2.5 kg'], ['Joint', 'footprint_to_base'], ['Joint type', 'fixed'], ['Parent', 'base_footprint']]);

  // A link with no geometry is still a selection: the row, and what the payload says.
  fireEvent.click(screen.getByRole('button', { name: 'Select shoulder_link' }));
  expect(drawn()).toBe('[["shoulder_link"],[]]');
  details = within(screen.getByRole('region', { name: 'Reference details' }));
  expect(facts('shoulder_link').map(([label]) => label)).toEqual(expect.arrayContaining(['Joint', 'Joint type', 'Parent']));
  expect(Object.fromEntries(facts('shoulder_link'))['Joint type']).toBe('revolute');
  // Its chip copies its reference into the description: the file, and the link by name.
  expect(details.getByLabelText('Chip shoulder_link').getAttribute('data-copy')).toBe('/work/arm.urdf#shoulder_link');

  fireEvent.click(details.getByRole('button', { name: 'Remove shoulder_link' }));
  expect(screen.queryByRole('region', { name: 'Reference details' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Select shoulder_link' }).getAttribute('aria-pressed')).toBe('false');
});

it('a link\'s card follows its parent: pressing the parent selects it there and in the viewport', () => {
  render(<Harness/>);
  fireEvent.click(screen.getByRole('button', { name: 'Expand shoulder_link' }));
  fireEvent.click(screen.getByRole('button', { name: 'Select elbow_link' }));
  const details = within(screen.getByRole('region', { name: 'Reference details' }));
  fireEvent.click(details.getByRole('button', { name: 'shoulder_link' }));
  expect(screen.getByRole('button', { name: 'Select shoulder_link' }).getAttribute('aria-pressed')).toBe('true');
  expect(drawn()).toBe('[["shoulder_link"],[]]');
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
  // Nothing found is the panel's to say, once, for every tab.
  expect(screen.getByText('Nothing matches “nothing here”')).toBeTruthy();

  // Typing never touched the tree's expansion.
  fireEvent.click(screen.getByRole('button', { name: 'Close search' }));
  expect(rows()).toEqual(['Select base_link', 'Select shoulder_link', 'Select camera_link']);
});

it('reveals a selected hit with its ancestors expanded when the filter is cleared', () => {
  const scrollIntoView = vi.fn();
  Element.prototype.scrollIntoView = scrollIntoView;
  render(<Harness/>);
  fireEvent.change(filter(), { target: { value: 'wrist_roll' } });
  fireEvent.keyDown(filter(), { key: 'Enter' });
  expect(drawn()).toBe('[["wrist_link"],[]]');
  expect(within(screen.getByRole('region', { name: 'Reference details' })).getByRole('region', { name: 'wrist_link' }).textContent).toContain('continuous');
  scrollIntoView.mockClear();
  fireEvent.keyDown(filter(), { key: 'Escape' });
  expect(filter().value).toBe('');
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
  const component = reference.getByRole('region', { name: 'flange' }).querySelector('[data-detail-facts]')!.textContent!;
  expect(component).toBe('Linkwrist_linkSize40 × 40 × 8 mm');
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
  fireEvent.click(screen.getByRole('button', { name: 'Close search' }));
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
  expect(within(screen.getByRole('list', { name: 'Robot links' })).getAllByRole('button', { pressed: true }).map(row => row.getAttribute('aria-label')))
    .toEqual(['Select base_link', 'Select shoulder_link']);
  // Several links are a chip each, and a reference each.
  expect(chipLabels()).toEqual(['Chip base_link', 'Chip shoulder_link']);
  expect(screen.getByRole('region', { name: 'Reference details' }).getAttribute('data-references')).toBe('[["base_link"],["shoulder_link"]]');
  fireEvent.click(screen.getByRole('button', { name: 'Select base_link' }), { metaKey: true });
  expect(drawn()).toBe('[["shoulder_link"],[]]');
  fireEvent.click(screen.getByRole('button', { name: 'Select base_link' }));
  expect(drawn()).toBe('[["base_link"],[]]');
});

it("a link's description is the link alone: a few key facts, its joint to its parent and the parent link, never its child links", () => {
  const item = robotLinkItem(robotLinkFacts(robot, 'shoulder_link'));
  // Its hover tip says what joint holds it.
  expect([item.title, item.tip]).toEqual(['shoulder_link', 'revolute']);
  expect([item.facts.map((fact: any) => fact.label), 'related' in item]).toEqual([['Mass', 'Joint', 'Joint type', 'Parent'], false]);
  // The root is said to be one, with nothing holding it.
  expect(robotLinkItem(robotLinkFacts(robot, 'base_footprint')).tip).toBe('Root link');
});

it("the hover tip's words for a robot are its link's name and the joint that holds it, or an object's name and link, building no facts", () => {
  let tip: (id: string) => string = () => '';
  function Probe() { tip = useRobotTip({ robot, components }); return null; }
  render(<Probe/>);
  expect([tip('shoulder_link'), tip('base_footprint'), tip('wrist_link:v1/object/0'), tip('nowhere')])
    .toEqual(['shoulder_link · revolute', 'base_footprint · Root link', 'flange · wrist_link', '']);
});

// A link picked in the view while the panel shows another tab waits for its tab: opened, the tree
// scrolls to the pick's row then (a row in a hidden tab has no place to be scrolled to).
it('scrolls to a link picked while another tab is open once its tab is shown', () => {
  const scrolled: string[] = [];
  // The rows scrolled to (the panel's tab strip brings its open tab into view too: not a row).
  const scrollIntoView = vi.fn(function (this: Element) { if (!this.closest('[role=tablist]')) scrolled.push(this.textContent || ''); });
  Object.assign(Element.prototype, { scrollIntoView });
  function Tabbed({ tab, pick }: { tab: string, pick: string }) {
    const selection = useLinkSelection({ scene, hidden: false, requestRender() {} });
    React.useEffect(() => { if (pick) selection.selectLink(pick); }, [pick]);
    return <FlatPanel mode="docked" open onClose={() => {}} label="Model panel" searchLabel="Search the model"
      sections={<><LinksSection robot={robot} components={components} parts={parts} selection={selection}/>
        <ToolPanel id="other" label="Other"><p>Other</p></ToolPanel></>}
      tab={tab} onTabChange={() => {}} width={FLAT_PANEL_DEFAULT_WIDTH} maxWidth={480} onWidthChange={() => {}} focusSearch={0} />;
  }
  try {
    const { rerender } = render(<Tabbed tab="other" pick="" />);
    rerender(<Tabbed tab="other" pick="wrist_link" />);
    expect(scrolled).toEqual([]);
    rerender(<Tabbed tab="tree" pick="wrist_link" />);
    expect(scrolled.at(-1)).toContain('wrist_link');
  } finally {
    delete (Element.prototype as any).scrollIntoView;
  }
});
