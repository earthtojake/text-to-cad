import { useState } from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import * as THREE from 'three';
import { createCadClient } from '@hardcore/core/client';
import { FileViewer } from '../../../dist/file-viewer/index.js';
import { createRobotRenderer } from '../../../dist/renderers/robot/index.js';
// Loaded with the file, not inside the first test: the registration imports it lazily.
import '../../../dist/renderers/robot/RobotRenderer.js';

// The robot renderer's tools and tool stack, mounted the way a host mounts it: the FileViewer over the
// real robot registration, a real CAD client whose backend is a fetch, the real description loader and
// the real robot scene graph (three.js objects need no WebGL). What is stood in for is the WebGL
// viewport alone — `ShellViewport` is a box that hands the renderer's overlay its viewport — and the
// two overlays that only draw into it: the Position knobs (present or not is the contract here, their
// drawing is the browser suite's) and the pointer pick, whose tap is a real ray through the real scene.

const box = (size: string, xyz: string) => `<visual><origin xyz="${xyz}"/><geometry><box size="${size}"/></geometry></visual>`;
const limit = (lower: number, upper: number) => `<limit lower="${lower}" upper="${upper}" effort="1" velocity="1"/>`;
const ARM_URDF = `<?xml version="1.0"?>
<robot name="arm">
  <link name="base_footprint"/>
  <link name="base">${box('0.4 0.4 0.1', '0 0 0.05')}</link>
  <link name="upper_arm">${box('0.5 0.08 0.08', '0.25 0 0')}</link>
  <link name="carriage">${box('0.1 0.1 0.1', '0 0 0')}</link>
  <link name="camera">${box('0.06 0.06 0.06', '0 0 0')}</link>
  <joint name="footprint" type="fixed"><parent link="base_footprint"/><child link="base"/></joint>
  <joint name="shoulder" type="revolute"><parent link="base"/><child link="upper_arm"/><origin xyz="0 0 0.2"/><axis xyz="0 1 0"/>${limit(-1.5708, 1.5708)}</joint>
  <joint name="lift" type="prismatic"><parent link="base"/><child link="carriage"/><origin xyz="-0.15 0.15 0.15"/><axis xyz="0 0 1"/>${limit(0, 0.3)}</joint>
  <joint name="camera_mount" type="fixed"><parent link="base"/><child link="camera"/><origin xyz="0.15 -0.15 0.13"/></joint>
</robot>
`;
const FILE = 'arm.urdf';

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

const json = (body: unknown) => new Response(JSON.stringify(body), { headers: { 'content-type': 'application/json' } });

async function openRobot() {
  const fetch = vi.fn(async (input: RequestInfo | URL) => {
    const url = new URL(String(input));
    if (url.pathname.endsWith('/__cad/catalog')) {
      return json({ rootId: 'one', entries: [{ kind: 'urdf', file: FILE, rootRelativeFile: FILE, url: `/${FILE}`, hash: 'one-arm-1', bytes: ARM_URDF.length }] });
    }
    if (url.pathname.endsWith('/__cad/server')) return json({ rootId: 'one', rootPath: '/models', backend: 'cadgen' });
    if (url.pathname.endsWith(`/${FILE}`)) return new Response(ARM_URDF);
    return new Response('', { status: 404 });
  });
  const client = createCadClient({ origin: 'http://viewer.test/one', workspaceId: 'one', pollIntervalMs: 0, fetch: fetch as typeof globalThis.fetch });
  await client.refresh();
  const renderers = [createRobotRenderer({ client })];
  const destination = { kind: 'composer', available: true };
  const host = {
    files: {
      id: 'one', rootName: 'one',
      stat: async (path: string) => ({ path, name: path, kind: 'file', size: ARM_URDF.length, extension: 'urdf' }),
      list: async () => [{ path: FILE, name: FILE, kind: 'file' }],
    },
    navigation: { openFile: noop },
    environment: { colorScheme: 'light' },
    clipboard: { writeText: async () => {}, readText: async () => '', writeImage: async () => {} },
    promptContext: { getSnapshot: () => destination, subscribe: () => noop, deliver: async () => ({ status: 'added', partIds: [] }) },
  };
  // The tab's state, held as a host holds it: the panel the person opened is the host's.
  function Pane() {
    const [state, setState] = useState<any>({ panel: null, renderers: {} });
    return <section data-testid="one"><FileViewer file={FILE} host={host as any} renderers={renderers} state={state} onStateChange={setState} /></section>;
  }
  render(<Pane />);
  const pane = screen.getByTestId('one');
  // A robot opens in Select, so its Links panel is in the stack once the robot has loaded.
  await waitFor(() => expect(pane.querySelector('[aria-label="Robot links"] li')).not.toBeNull());
  const tools = () => within(pane).getByRole('group', { name: 'Interaction tools' });
  const robot = {
    pane, client,
    tool: (name: string) => within(tools()).getByRole('button', { name }),
    toolNames: () => within(tools()).getAllByRole('button').map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`),
    // The tool stack's panels on screen, top to bottom.
    stack: () => [...pane.querySelectorAll('[data-cad-tool-stack] [data-tool-panel]')]
      .filter(panel => !panel.closest('[hidden]')).map(panel => panel.getAttribute('aria-label')),
    // The nav row's panel toggles, each with whether its panel is the open one.
    panels: () => [...pane.querySelectorAll('[data-file-panel]')].map(button => `${button.getAttribute('aria-label')}:${button.getAttribute('aria-pressed')}`),
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

  // Display is not a tool: its popover opens over Position and leaves it the tool, knobs and panel.
  expect(within(robot.pane).queryByRole('button', { name: 'Display' })).toBeNull();
  fireEvent.click(within(robot.pane).getByRole('button', { name: 'Display settings' }));
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

  // With the file tree open, a link picked in the viewport and the Position tool leave it open:
  // their panels are the stack's, never the host's column.
  robot.open('Select');
  expect(robot.panels()).toEqual(['Show files:false']);
  fireEvent.click(robot.pane.querySelector('[data-file-panel="tree"]')!);
  await waitFor(() => expect(within(robot.pane).getByPlaceholderText('Filter files…')).toBeTruthy());
  expect(robot.panels()).toEqual(['Hide files:true']);
  robot.tapUpperArm();
  await waitFor(() => expect(robot.pressedRows()).toHaveLength(1));
  expect(robot.panels()).toEqual(['Hide files:true']);
  expect(robot.stack()).toEqual(['Links', 'Reference details']);
  robot.open('Position');
  expect(robot.panels()).toEqual(['Hide files:true']);
  expect(robot.stack()).toEqual(['Position controls']);
  robot.client.dispose();
});
