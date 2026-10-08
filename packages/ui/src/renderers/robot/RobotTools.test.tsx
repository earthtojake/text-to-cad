import { useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
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
// (`GET /__cad/robot`: the payload it resolved for the description, and the meshes that names), the
// real robot loader and the real robot scene graph (three.js objects need no WebGL). What is stood in
// for is the WebGL viewport alone — `ShellViewport` is a box that hands the renderer's overlay its
// viewport — and the two overlays that only draw into it: the Position knobs (present or not is the
// contract here, their drawing is the browser suite's) and the pointer pick, whose tap is a real ray
// through the real scene.

const FILE = '/models/arm.urdf';
const payload = () => fixturePayload('arm.urdf');

// ---- the WebGL stand-ins ------------------------------------------------------------------------
const picks = vi.hoisted(() => ({ latest: null as null | { enabled: boolean; scene: any; onPick: (hit: unknown, modifiers: { multiSelect: boolean }) => void } }));
vi.mock('../../../dist/renderers/kit/shell/ShellViewport.js', async () => {
  const { createElement, forwardRef: forward, useImperativeHandle: handle, useRef: ref } = await import('react');
  return {
    default: forward(function ShellViewport({ children }: { children?: (viewport: object) => unknown }, viewerRef) {
      const runtimeRef = ref(null), hostRef = ref(null), mountRef = ref(null);
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

async function openRobot() {
  // The file as the catalog lists it now: a save is a new revision, under a new version of its URL,
  // and cadgen's answer for it is the payload of that revision.
  const served = { revision: 1, payload: payload() };
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input), 'http://viewer.test');
    if (url.pathname.endsWith('/__cad/catalog')) {
      return json({ entries: [{ kind: 'urdf', file: FILE, url: `/arm.urdf?v=${served.revision}`, hash: `one-arm-${served.revision}`, bytes: 1 }] });
    }
    if (url.pathname.endsWith('/__cad/server')) return json({ backend: 'cadgen' });
    if (url.pathname.endsWith('/__cad/robot')) {
      return url.searchParams.get('file') === FILE ? json(served.payload) : json({ error: `${url.searchParams.get('file')}: no such description` }, 404);
    }
    if (/\/(primitives|meshes)\/[^/]+\.glb$/.test(url.pathname)) return new Response(fixtureGlb(url.pathname), { headers: { 'content-type': 'model/gltf-binary' } });
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
    clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
    promptContext: { getSnapshot: () => destination, subscribe: () => noop, deliver: async () => ({ status: 'added', partIds: [] }) },
  };
  // The tab's state, held as a host holds it.
  function Pane() {
    const [state, setState] = useState<any>({ renderers: {} });
    return <section data-testid="one"><FileViewer file={FILE} host={host as any} renderers={renderers} state={state} onStateChange={setState} /></section>;
  }
  render(<Pane />);
  const pane = screen.getByTestId('one');
  // A robot opens in Select, so its Links panel is in the stack once the robot has loaded.
  await waitFor(() => expect(pane.querySelector('[aria-label="Robot links"] li')).not.toBeNull());
  const tools = () => within(pane).getByRole('group', { name: 'Interaction tools' });
  const robot = {
    pane, client,
    /** Save the file again, as cadgen now resolves it, and let the catalog say so: the robot on screen loads the new revision. */
    async publish(next: ReturnType<typeof payload>) {
      served.revision += 1;
      served.payload = next;
      await act(async () => { await client.refresh(); });
    },
    tool: (name: string) => within(tools()).getByRole('button', { name }),
    toolNames: () => within(tools()).getAllByRole('button').map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`),
    // The tool stack's panels on screen, top to bottom.
    stack: () => [...pane.querySelectorAll('[data-cad-tool-stack] [data-tool-panel]')]
      .filter(panel => !panel.closest('[hidden]')).map(panel => panel.getAttribute('aria-label')),
    knobs: () => pane.querySelectorAll('[data-cad-joint-handles]').length,
    posedMark: () => robot.tool('Position').querySelectorAll('[data-position-custom]').length,
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
      expect(hit).toMatchObject({ kind: 'link', linkName: 'upper_arm' });
      act(() => pick.onPick(hit, { multiSelect: false }));
    },
    pressedRows: () => [...pane.querySelectorAll('[aria-label="Robot tree area"] button[aria-pressed="true"]')].map(button => button.getAttribute('aria-label')),
  };
  return robot;
}

it('robot Select defaults match Links and Position remains an explicit tool', async () => {
  const robot = await openRobot();
  expect(robot.toolNames()).toEqual(['Select:true', 'Position:false']);
  expect(robot.stack()).toEqual(['Links']);
  expect(robot.tool('Select').querySelectorAll('svg.lucide-mouse-pointer-2')).toHaveLength(1);
  expect(robot.knobs()).toBe(0);

  robot.open('Position');
  expect(robot.tool('Position').getAttribute('aria-pressed')).toBe('true');
  expect(robot.stack()).toEqual(['Position controls']);
  expect(robot.knobs()).toBe(1);

  // Display is not a tool: its dropdown, from the navbar's right end, opens over Position and leaves
  // it the tool, with its knobs and panel; Escape puts it away.
  fireEvent.click(within(robot.pane.querySelector<HTMLElement>('[data-view-controls]')!).getByRole('button', { name: 'Display' }));
  await waitFor(() => expect(document.querySelector('[data-display-popover]')).not.toBeNull());
  expect(robot.toolNames()).toEqual(['Select:false', 'Position:true']);
  expect(robot.stack()).toEqual(['Position controls']);
  expect(robot.knobs()).toBe(1);
  fireEvent.keyDown(document.activeElement || document.body, { key: 'Escape' });
  await waitFor(() => expect(document.querySelector('[data-display-popover]')).toBeNull());
  expect(robot.toolNames()).toEqual(['Select:false', 'Position:true']);

  // The Position tool's icon carries a dot while the robot is posed off its default, until Reset.
  expect(robot.posedMark()).toBe(0);
  robot.type('shoulder', '25');
  await waitFor(() => expect(robot.posedMark()).toBe(1));
  fireEvent.click(robot.position().getByRole('button', { name: 'Reset' }));
  await waitFor(() => expect(robot.posedMark()).toBe(0));

  // Its X puts Position down, back to Select.
  fireEvent.click(robot.position().getByRole('button', { name: 'Close position' }));
  expect(robot.toolNames()).toEqual(['Select:true', 'Position:false']);
  expect(robot.stack()).toEqual(['Links']);
  expect(robot.knobs()).toBe(0);
  // Select is the default tool: pressing it again leaves it the tool.
  robot.open('Select');
  expect(robot.tool('Select').getAttribute('aria-pressed')).toBe('true');
  expect(robot.knobs()).toBe(0);
  robot.client.dispose();
});

it('a robot is a 3D view: Display and Preview sit at the navbar\'s right end', async () => {
  const robot = await openRobot();
  const actions = robot.pane.querySelector<HTMLElement>('[data-viewer-navbar] [data-view-controls]')!;
  expect([...actions.querySelectorAll('button')].map(button => button.getAttribute('aria-label'))).toEqual(['Display', 'Preview']);
  robot.client.dispose();
});

it('robot Links and Position are each their tool\'s panel, and no pick or tool opens or turns the host\'s column', async () => {
  const robot = await openRobot();
  expect(robot.stack()).toEqual(['Links']);
  expect(within(robot.pane).queryAllByRole('tab')).toHaveLength(0);
  robot.open('Position');
  expect(robot.stack()).toEqual(['Position controls']);
  robot.type('shoulder', '30');
  // Putting Position down hides its panel; picking it up again shows the pose it was left in.
  robot.open('Select');
  expect(robot.jointField('shoulder').closest('[hidden]')).not.toBeNull();
  robot.open('Position');
  expect(robot.jointField('shoulder').closest('[hidden]')).toBeNull();
  expect(robot.jointField('shoulder').value).toBe('30°');

  // A link picked in the viewport and the Position tool show their panels in the stack.
  robot.open('Select');
  robot.tapUpperArm();
  await waitFor(() => expect(robot.pressedRows()).toHaveLength(1));
  expect(robot.stack()).toEqual(['Links', 'Reference details']);
  robot.open('Position');
  expect(robot.stack()).toEqual(['Position controls']);
  robot.client.dispose();
});

it("robot Links closes by its X and Select brings it back: marked while it is closed, a press while Select is the tool opens it, and from another tool a press only takes Select up", async () => {
  const robot = await openRobot();
  const mark = () => robot.tool('Select').querySelector('[data-tool-panel-closed]');
  expect([robot.stack(), mark()]).toEqual([['Links'], null]);
  fireEvent.click(within(robot.pane).getByRole('button', { name: 'Close links' }));
  expect(robot.stack()).toEqual([]);
  expect(mark()).not.toBeNull();
  expect(robot.tool('Select').getAttribute('aria-description')).toBe('Links closed');
  // A pick still shows its Reference: a panel of its own, apart from the closed tree.
  robot.tapUpperArm();
  await waitFor(() => expect(robot.stack()).toEqual(['Reference details']));
  // From Position, Select is only taken up: the tree stays closed.
  robot.open('Position');
  robot.open('Select');
  expect(robot.toolNames()).toEqual(['Select:true', 'Position:false']);
  expect(robot.stack()).toEqual([]);
  expect(mark()).not.toBeNull();
  // Pressed while it is the tool, it opens Links again, as it was.
  robot.open('Select');
  expect(robot.stack()).toEqual(['Links']);
  expect(mark()).toBeNull();
  expect(robot.pane.querySelector('[aria-label="Robot links"] li')).not.toBeNull();
  robot.client.dispose();
});

it('on a phone robot Links starts closed, Select marked, until Select is pressed', async () => {
  vi.spyOn(HTMLElement.prototype, 'getBoundingClientRect').mockReturnValue(
    { x: 0, y: 0, left: 0, top: 0, right: 390, bottom: 844, width: 390, height: 844, toJSON: noop } as DOMRect);
  const robot = await openRobot();
  expect(robot.pane.querySelector('[data-viewer-layout]')!.getAttribute('data-viewer-layout')).toBe('mobile');
  expect(robot.stack()).toEqual([]);
  expect(robot.tool('Select').querySelector('[data-tool-panel-closed]')).not.toBeNull();
  robot.open('Select');
  expect(robot.stack()).toEqual(['Links']);
  expect(robot.tool('Select').querySelector('[data-tool-panel-closed]')).toBeNull();
  robot.client.dispose();
});

it('a new revision of the robot keeps its pose while its controls and named poses are the same, and opens at its opening pose when they changed', async () => {
  const robot = await openRobot();
  robot.open('Position');
  robot.type('shoulder', '25');
  await waitFor(() => expect(robot.jointField('shoulder').value).toBe('25°'));
  // The robot on screen is the scene the viewport's pick is handed: a new revision is a new one.
  const scene = () => picks.latest!.scene;
  const before = scene();

  // Saved again with the same articulation (the upper arm grew): the pose stays, and Position with it.
  const longer = payload();
  longer.links.find((link: any) => link.name === 'upper_arm').visuals[0].size = [1, 0.08, 0.08];
  await robot.publish(longer);
  await waitFor(() => expect(scene()).not.toBe(before));
  expect(robot.jointField('shoulder').value).toBe('25°');
  expect(robot.toolNames()).toEqual(['Select:false', 'Position:true']);

  // The shoulder's range changed: the robot opens at its opening pose, though 25° would still fit.
  const kept = scene();
  const narrower = payload();
  for (const row of [narrower.articulation.controls, narrower.articulation.handles].map((rows: any[]) => rows.find(row => row.id === 'shoulder'))) {
    row.min = -57.3;
    row.max = 57.3;
  }
  await robot.publish(narrower);
  await waitFor(() => expect(scene()).not.toBe(kept));
  expect(robot.jointField('shoulder').value).toBe('0°');
  robot.client.dispose();
});
