import { useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { createCadClient } from '@text-to-cad/core/client';
import { FileViewer } from '../../../dist/file-viewer/index.js';
import { createRobotRenderer } from '../../../dist/renderers/robot/index.js';
// Loaded with the file, not inside the first test: the registration imports it lazily.
import '../../../dist/renderers/robot/RobotRenderer.js';
import { fixtureGlb, fixturePayload } from './__tests__/robotFixtures.js';


// The robot renderer's tools and tool stack, mounted the way a host mounts it: the FileViewer over the
// real robot registration, a real CAD client whose backend is a fetch answering what cadgen answers
// (the resolved robot payload and the stored meshes it names), the
// real robot loader and the real robot scene graph (three.js objects need no WebGL). What is stood in
// for is the WebGL viewport alone — `ShellViewport` is a box that hands the renderer's overlay its
// viewport — and the two overlays that only draw into it: the Position knobs (present or not is the
// contract here, their drawing is the browser suite's) and the pointer pick, whose tap is a real ray
// through the real scene.

const FILE = '/models/arm.urdf';
// The checked-in native payload, narrowed to the two links and one control this tool flow uses.
// Its primitive GLBs are the exact objects cadgen wrote for the fixture description.
const robotPayload = () => {
  const robot = fixturePayload('arm.urdf');
  robot.root = 'base';
  robot.links = robot.links.filter((link: any) => ['base', 'upper_arm'].includes(link.name));
  robot.joints = robot.joints.filter((joint: any) => joint.name === 'shoulder');
  robot.visuals = robot.visuals.filter((visual: any) => ['base', 'upper_arm'].includes(visual.link));
  robot.articulation.controls = robot.articulation.controls.filter((control: any) => control.id === 'shoulder');
  robot.articulation.joints = robot.articulation.joints.filter((joint: any) => joint.id === 'shoulder')
    .map((joint: any) => ({ ...joint, parent: null }));
  robot.articulation.carries = { shoulder: ['upper_arm'] };
  robot.articulation.handles = robot.articulation.handles.filter((handle: any) => handle.id === 'shoulder');
  robot.articulation.opening = { shoulder: 0 };
  return robot;
};
let nextRobot = 0;

// ---- the WebGL stand-ins ------------------------------------------------------------------------
const picks = vi.hoisted(() => ({ latest: null as null | { enabled: boolean; scene: any; onPick: (hit: unknown, modifiers: { multiSelect: boolean }) => void } }));
// The scene Preview's own viewport draws, while it is open (`PreviewView.jsx`).
const previewView = vi.hoisted(() => ({ scene: null as any }));
vi.mock('../../../dist/renderers/kit/shell/ShellViewport.js', async () => {
  const { createElement, forwardRef: forward, useImperativeHandle: handle, useRef: ref } = await import('react');
  return {
    default: forward(function ShellViewport({ children, preview, scene }: { children?: (viewport: object) => unknown, preview?: boolean, scene?: any }, viewerRef) {
      const runtimeRef = ref(null), hostRef = ref(null), mountRef = ref(null);
      if (preview) previewView.scene = scene ?? null;
      handle(viewerRef, () => ({
        prepareViewSettings: async () => {}, presentViewSettings() {}, requestRender() {}, syncSceneBounds() {},
        getPerspective: () => null, captureScreenshotBlob: async () => new Blob(['png'], { type: 'image/png' }),
      }), []);
      const viewport = { runtimeRef, hostRef, mountRef, viewerReadyTick: 1, commitScene: () => true };
      return createElement('div', { ref: hostRef, 'data-test-viewport': '' },
        createElement('canvas', null), typeof children === 'function' ? children(viewport) : children);
    }),
  };
});
vi.mock('../../../dist/renderers/kit/tools/pose/JointHandleOverlay.js', async () => {
  const { createElement } = await import('react');
  return { default: () => createElement('div', { 'data-cad-joint-handles': '' }) };
});
vi.mock('../../../dist/renderers/kit/tools/select/usePointerPick.js', async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return { ...actual, PointerPick: (props: any) => { picks.latest = props; return null; } };
});

const noop = () => {};
beforeEach(() => {
  picks.latest = null;
  vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => setTimeout(() => callback(performance.now()), 0));
  vi.stubGlobal('cancelAnimationFrame', (handle: number) => clearTimeout(handle));
  vi.stubGlobal('matchMedia', (query: string) => ({ matches: false, media: query, addEventListener: noop, removeEventListener: noop, addListener: noop, removeListener: noop }));
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
    { x: 0, y: 0, left: 0, top: 0, right: 1200, bottom: 720, width: 1200, height: 720, toJSON: noop } as DOMRect);
  Element.prototype.scrollIntoView ??= noop;
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.restoreAllMocks(); });

const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'content-type': 'application/json' } });

async function openRobot({ phone = false } = {}) {
  // The file as the catalog lists it now: a save is a new revision, under a new version of its URL,
  // and the loader reads cadgen's resolved payload for that revision.
  const id = ++nextRobot;
  const served = { revision: 1, robot: robotPayload() };
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://viewer.test');
    if (url.pathname.endsWith('/__cad/catalog')) {
      return json({ entries: [{ kind: 'urdf', file: FILE, url: `/arm.urdf?v=${served.revision}`, hash: `tools-arm-${id}-${served.revision}`, bytes: 1 }] });
    }
    if (url.pathname.endsWith('/__cad/server')) return json({ backend: 'cadgen' });
    if (url.pathname.endsWith('/__cad/robot')) {
      expect(url.searchParams.get('file')).toBe(FILE);
      return json(served.robot);
    }
    if (/\/primitives\/[^/]+\.glb$/.test(url.pathname)) {
      return new Response(fixtureGlb(url.pathname), { headers: { 'content-type': 'model/gltf-binary' } });
    }
    return new Response('', { status: 404 });
  });
  const client = createCadClient({ origin: 'http://viewer.test/one', pollIntervalMs: 0, fetch: fetch as typeof globalThis.fetch });
  await client.refresh();
  const renderers = [createRobotRenderer({ client })];
  const destination = { kind: 'composer', available: true };
  const host = {
    files: {
      id: 'one',
      stat: async (path: string) => ({ path, name: path.split('/').pop(), kind: 'file', size: 1, extension: 'urdf' }),
    },
    navigation: { openFile: noop },
    environment: { colorScheme: 'light' },
    clipboard: { writeText: async () => {}, writeImage: async () => {} },
    promptContext: { getSnapshot: () => destination, subscribe: () => noop, deliver: async () => ({ status: 'added', partIds: [] }) },
  };
  // The tab's state, held as a host holds it.
  function Pane() {
    const [state, setState] = useState<any>({ renderers: {} });
    return <section data-testid="one"><FileViewer file={FILE} host={host as any} renderers={renderers} state={state} onStateChange={setState} /></section>;
  }
  render(<Pane />);
  const pane = screen.getByTestId('one');
  // Its Links are in the file sidebar once the robot has loaded; on a phone the sidebar's tiles
  // lead the strip, which comes with the robot.
  await waitFor(() => expect(phone ? within(pane).queryByRole('group', { name: 'Interaction tools' }) : pane.querySelector('[aria-label="Robot links"] li')).not.toBeNull());
  const tools = () => within(pane).getByRole('group', { name: 'Interaction tools' });
  const robot = {
    pane, client,
    /** Save the file again, as cadgen now resolves it, and let the catalog say so: the robot on screen loads the new revision. */
    async publish(next: ReturnType<typeof robotPayload>) {
      served.revision += 1;
      served.robot = next;
      await act(async () => { await client.refresh(); });
    },
    tool: (name: string) => within(tools()).getByRole('button', { name }),
    // The strip's tools (its buttons pressed or not, before the view's controls), and what Select's chevron says it picks.
    toolNames: () => within(tools()).getAllByRole('button').filter(button => button.hasAttribute('aria-pressed') && !button.closest('[data-view-controls]'))
      .map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`),
    filter: () => tools().querySelector('[data-select-filter-trigger]')!.getAttribute('aria-label'),
    /** Choose `mode` from Select's menu ("all", "links" or "position"), which puts the menu away. */
    async choose(mode: string) {
      const user = userEvent.setup();
      await user.click(tools().querySelector<HTMLElement>('[data-select-filter-trigger]')!);
      await user.click(document.querySelector<HTMLElement>(`[data-select-filter="${mode}"]`)!);
      await waitFor(() => expect(document.querySelector('[data-select-filter]')).toBeNull());
    },
    menuItems: () => [...document.querySelectorAll('[data-select-filter]')].map(item => `${item.textContent}:${item.getAttribute('aria-checked')}`),
    // The tool stack's panels on screen, top to bottom, and the file sidebar's sections.
    stack: () => [...pane.querySelectorAll('[data-cad-tool-stack] [data-tool-panel]')]
      .filter(panel => !panel.closest('[hidden]')).map(panel => panel.getAttribute('aria-label')),
    sidebar: () => [...pane.querySelectorAll('[data-cad-file-sidebar] [data-tool-panel]')]
      .filter(panel => !panel.closest('[hidden]')).map(panel => panel.getAttribute('aria-label')),
    knobs: () => pane.querySelectorAll('[data-cad-joint-handles]').length,
    jointField: (name: string) => within(pane).getByLabelText(`${name} value in deg`) as HTMLInputElement,
    position: () => within(pane.querySelector('[data-tool-panel][aria-label="Position controls"]') as HTMLElement),
    open: (name: string) => fireEvent.click(robot.tool(name)),
    type(name: string, value: string) {
      const field = robot.jointField(name);
      fireEvent.change(field, { target: { value } });
      fireEvent.keyDown(field, { key: 'Enter' });
    },
    /** A tap on the model: a real ray, down onto the upper arm, through the robot scene's own pick. */
    tapUpperArm() {
      const pick = picks.latest!;
      expect(pick.enabled).toBe(true);
      const root = pick.scene.object3D as THREE.Object3D;
      root.updateMatrixWorld();
      const from = root.localToWorld(new THREE.Vector3(0.25, 0, 5));
      const onto = root.localToWorld(new THREE.Vector3(0.25, 0, 0.2));
      const hit = pick.scene.pick(new THREE.Ray(from, onto.sub(from).normalize()));
      // Every visual is a component: the pick names the upper arm's visual, on its link.
      expect(hit).toMatchObject({ kind: 'component', linkName: 'upper_arm', componentId: 'upper_arm:v1' });
      act(() => pick.onPick(hit, { multiSelect: false }));
    },
    pressedRows: () => [...pane.querySelectorAll('[aria-label="Robot tree area"] button[aria-pressed="true"]')].map(button => button.getAttribute('aria-label')),
  };
  return robot;
}

// The strip with Select in hand: a robot's four tools (`robot/tools.js`).
const SELECT_IN_HAND = ['Select:true', 'Pencil:false', 'Shapes:false', 'Measure:false', 'Clip:false'];

it('robot Select opens in hand, before Pencil, Shapes, Measure and Clip: it picks links and drags the knobs, and its filter picks either alone', async () => {
  const robot = await openRobot();
  expect([robot.toolNames(), robot.filter()]).toEqual([SELECT_IN_HAND, 'Selection filter: everything']);
  expect([robot.sidebar(), robot.stack()]).toEqual([['Links', 'Position controls'], []]);
  expect(robot.tool('Select').querySelectorAll('svg.lucide-mouse-pointer-2')).toHaveLength(1);
  expect([robot.knobs(), picks.latest!.enabled]).toEqual([1, true]);

  // The chevron's menu: one choice of what a click takes — All, the links alone, or the knobs alone.
  const user = userEvent.setup();
  await user.click(robot.pane.querySelector<HTMLElement>('[data-select-filter-trigger]')!);
  expect(robot.menuItems()).toEqual(['All:true', 'Links:false', 'Position:false']);
  await user.keyboard('{Escape}');
  await robot.choose('links');
  expect([robot.filter(), robot.knobs(), picks.latest!.enabled]).toEqual(['Selection filter: Links', 0, true]);
  await robot.choose('position');
  expect([robot.filter(), robot.knobs(), picks.latest!.enabled]).toEqual(['Selection filter: Position', 1, false]);
  expect(robot.toolNames()).toEqual(SELECT_IN_HAND);

  // Display is not a tool: its menu (the modes and Grid), from its tile at the strip's end, opens over
  // Select and leaves it the tool, with its knobs; Escape puts it away.
  await user.click(within(robot.pane.querySelector<HTMLElement>('[data-cad-toolbar] [data-view-controls]')!).getByRole('button', { name: /^Display mode: / }));
  await waitFor(() => expect(document.querySelector('[role=menu][aria-label="Display"]')).not.toBeNull());
  expect([robot.toolNames(), robot.knobs()]).toEqual([SELECT_IN_HAND, 1]);
  await user.keyboard('{Escape}');
  await waitFor(() => expect(document.querySelector('[role=menu][aria-label="Display"]')).toBeNull());
  expect(robot.toolNames()).toEqual(SELECT_IN_HAND);

  // A pose off its default stays in the section when the filter puts the knobs away; its Pose row
  // says the joints were set by hand.
  robot.type('shoulder', '25');
  await robot.choose('links');
  expect([robot.filter(), robot.knobs()]).toEqual(['Selection filter: Links', 0]);
  expect(robot.jointField('shoulder').value).toBe('25°');
  expect(robot.position().getByRole('button', { name: /^Pose: / }).getAttribute('aria-label')).toBe('Pose: Custom');
  // Select is the only tool: pressing it again leaves it the tool, and its filter as it was.
  robot.open('Select');
  expect([robot.toolNames(), robot.filter(), robot.knobs()]).toEqual([SELECT_IN_HAND, 'Selection filter: Links', 0]);
  robot.client.dispose();
});

it("a robot is a 3D view: Projection, Display and Preview end the strip, in the section of Clip's, one rule in all, the navbar holding none of them", async () => {
  const robot = await openRobot();
  const strip = within(robot.pane).getByRole('group', { name: 'Interaction tools' });
  const actions = strip.querySelector<HTMLElement>('[data-view-controls]')!;
  // Two sections: the tools that pick, a rule, then Clip and the view's controls, nothing between them.
  expect(strip.querySelectorAll('[data-strip-rule]')).toHaveLength(1);
  expect(actions.previousElementSibling?.getAttribute('aria-label')).toBe('Clip');
  expect([...actions.querySelectorAll('button')].map(button => button.getAttribute('aria-label'))).toEqual(['Projection: Orthographic', 'Display mode: Solid', 'Preview']);
  expect(robot.pane.querySelectorAll('[data-viewer-navbar] [data-view-controls] button')).toHaveLength(0);
  robot.client.dispose();
});

it('robot Links and Position are the file sidebar\'s whatever Select picks, a Position control leaves the tool and its filter, and no pick opens or turns the host\'s column', async () => {
  const robot = await openRobot();
  expect(within(robot.pane).queryAllByRole('tab')).toHaveLength(0);
  // With the knobs put away, Position's section is on screen and drives the joints all the same.
  await robot.choose('links');
  expect(robot.sidebar()).toEqual(['Links', 'Position controls']);
  robot.type('shoulder', '30');
  expect(robot.jointField('shoulder').closest('[hidden]')).toBeNull();
  expect(robot.jointField('shoulder').value).toBe('30°');

  // A visual picked in the viewport is Quick Edit's chip, not a panel; the sidebar is as it was.
  robot.tapUpperArm();
  await waitFor(() => expect(robot.pressedRows()).toHaveLength(1));
  expect(robot.pane.querySelectorAll('[data-quick-edit-ref]')).toHaveLength(1);
  expect([robot.sidebar(), robot.stack()]).toEqual([['Links', 'Position controls'], []]);
  // Reaching for a Position control changes neither the tool nor what it picks.
  fireEvent.pointerDown(robot.jointField('shoulder'));
  expect([robot.toolNames(), robot.filter(), robot.knobs()]).toEqual([SELECT_IN_HAND, 'Selection filter: Links', 0]);
  robot.client.dispose();
});

it('robot Links and Position are the file sidebar\'s tiles whatever Select picks: a tile opens its section alone, its X or the tile closes it, and it never folds', async () => {
  const robot = await openRobot();
  const tiles = () => within(within(robot.pane).getByRole('group', { name: 'File sidebar' })).getAllByRole('button');
  const pressed = () => tiles().filter(tile => tile.getAttribute('aria-pressed') === 'true').map(tile => tile.getAttribute('aria-label'));
  const links = () => robot.pane.querySelector<HTMLElement>('[data-tool-panel][aria-label="Links"]')!;
  expect([tiles().map(tile => tile.getAttribute('aria-label')), pressed(), robot.toolNames()]).toEqual([['Links', 'Position'], [], SELECT_IN_HAND]);
  await robot.choose('position');
  expect([robot.filter(), robot.sidebar()]).toEqual(['Selection filter: Position', ['Links', 'Position controls']]);
  fireEvent.click(tiles()[0]);
  expect([pressed(), links().hasAttribute('data-sidebar-closed'), robot.pane.querySelector('aside[data-cad-file-sidebar]')!.hasAttribute('data-open')]).toEqual([['Links'], false, true]);
  expect(within(links()).queryByRole('button', { name: /^(?:Collapse|Expand) links$/ })).toBeNull();
  // One section at a time: Position's tile takes Links' place.
  fireEvent.click(tiles()[1]);
  expect([pressed(), links().hasAttribute('data-sidebar-closed')]).toEqual([['Position'], true]);
  fireEvent.click(tiles()[0]);
  fireEvent.click(within(links()).getByRole('button', { name: 'Close links' }));
  expect([pressed(), robot.pane.querySelector('aside[data-cad-file-sidebar]')!.hasAttribute('data-open')]).toEqual([[], false]);
  robot.client.dispose();
});

it('on a phone a robot\'s sidebar is one tile beside the strip, opening a panel of Links and Position tabs', async () => {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
    { x: 0, y: 0, left: 0, top: 0, right: 390, bottom: 844, width: 390, height: 844, toJSON: noop } as DOMRect);
  const robot = await openRobot({ phone: true });
  expect(robot.pane.querySelector('[data-viewer-layout]')!.getAttribute('data-viewer-layout')).toBe('mobile');
  const strip = within(robot.pane).getByRole('group', { name: 'Interaction tools' });
  const toggle = within(robot.pane).getByRole('button', { name: 'Sidebar' });
  expect([strip.contains(toggle), robot.pane.querySelectorAll('[data-file-sidebar-tools] button').length]).toEqual([false, 1]);
  fireEvent.click(toggle);
  await waitFor(() => expect(robot.pane.querySelector('aside[data-cad-file-sidebar]')!.hasAttribute('data-open')).toBe(true));
  // Its first section, under a tab per section; a phone's panel: its own width, and no grip.
  expect([...robot.pane.querySelectorAll('[data-file-sidebar-tab]')].map(tab => [tab.getAttribute('aria-label'), tab.getAttribute('data-state')]))
    .toEqual([['Links', 'on'], ['Position', 'off']]);
  const aside = robot.pane.querySelector<HTMLElement>('aside[data-cad-file-sidebar]')!;
  expect([aside.style.width, aside.querySelector('[data-file-sidebar-corner]')]).toEqual(['288px', null]);
  fireEvent.click(robot.pane.querySelector('[data-file-sidebar-tab="position"]')!);
  await waitFor(() => expect(robot.jointField('shoulder')).toBeTruthy());
  expect(robot.pane.querySelector('[data-tool-panel][aria-label="Links"]')!.hasAttribute('data-sidebar-closed')).toBe(true);
  robot.client.dispose();
});

it('a new revision of the robot keeps its pose while its controls and named poses are the same, and opens at its opening pose when they changed', async () => {
  const robot = await openRobot();
  await robot.choose('position');
  robot.type('shoulder', '25');
  await waitFor(() => expect(robot.jointField('shoulder').value).toBe('25°'));
  // The robot on screen is the scene the viewport's pick is handed: a new revision is a new one.
  const scene = () => picks.latest!.scene;
  const before = scene();

  // Saved again with the same articulation (the upper arm's visual moved): the pose stays,
  // and Select's filter with it. The primitive's stored mesh is unchanged.
  const shifted = robotPayload();
  shifted.links.find((link: any) => link.name === 'upper_arm').visuals[0].origin.xyz[0] += 0.2;
  shifted.visuals.find((visual: any) => visual.link === 'upper_arm').placement[3] += 0.2;
  await robot.publish(shifted);
  await waitFor(() => expect(scene()).not.toBe(before));
  expect(robot.jointField('shoulder').value).toBe('25°');
  expect([robot.toolNames(), robot.filter(), robot.knobs()]).toEqual([SELECT_IN_HAND, 'Selection filter: Position', 1]);

  // The shoulder's range changed: the robot opens at its opening pose, though 25° would still fit.
  const kept = scene();
  const narrower = robotPayload();
  narrower.joints[0].limit = { ...narrower.joints[0].limit, lower: -1, upper: 1 };
  for (const control of [...narrower.articulation.controls, ...narrower.articulation.handles]) {
    control.min = -180 / Math.PI;
    control.max = 180 / Math.PI;
  }
  await robot.publish(narrower);
  await waitFor(() => expect(scene()).not.toBe(kept));
  expect(robot.jointField('shoulder').value).toBe('0°');
  robot.client.dispose();
});


it("Preview draws a robot of its own at the opening pose; the tools view's robot keeps its pose throughout, and its values", async () => {
  const robot = await openRobot();
  const frameOf = (scene: any) => Array.from(scene.linkFrames().get('upper_arm'));
  const matrix = () => frameOf(picks.latest!.scene);
  const opening = matrix();
  robot.type('shoulder', '30');
  const posed = matrix();
  expect(posed).not.toEqual(opening);
  previewView.scene = null;
  await userEvent.setup().click(within(robot.pane).getByRole('button', { name: 'Preview' }));
  await waitFor(() => expect(previewView.scene).not.toBeNull());
  expect(previewView.scene).not.toBe(picks.latest!.scene);
  await waitFor(() => expect(frameOf(previewView.scene)).toEqual(opening));
  expect(matrix()).toEqual(posed);
  await userEvent.setup().click(screen.getByRole('button', { name: 'Exit preview', exact: true }));
  expect(matrix()).toEqual(posed);
  expect(robot.jointField('shoulder').value).toBe('30°');
  robot.client.dispose();
});

it('one motion at a time on a robot: Clip turned on puts the joints back, and a joint moved takes Clip off', async () => {
  const robot = await openRobot();
  robot.type('shoulder', '25');
  await waitFor(() => expect(robot.jointField('shoulder').value).toBe('25°'));
  robot.open('Clip');
  const clip = () => within(robot.pane).getByRole('slider', { name: 'Clip amount' });
  const cut = () => clip().getAttribute('aria-valuenow');
  fireEvent.keyDown(clip(), { key: 'End' });
  await waitFor(() => expect([cut(), robot.jointField('shoulder').value]).toEqual(['100', '0°']));
  robot.type('shoulder', '10');
  await waitFor(() => expect([cut(), robot.jointField('shoulder').value]).toEqual(['0', '10°']));
  robot.client.dispose();
});
