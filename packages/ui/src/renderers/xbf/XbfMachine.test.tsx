import React from 'react';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import FlatPanel from '../../../dist/renderers/kit/shell/FlatPanel.js';
import XbfPositionSection, { useXbfPose } from '../../../dist/renderers/xbf/XbfPositionSection.js';
import { useMachineMirror } from '../../../dist/renderers/xbf/useMachineMirror.js';

// Position's Machine row: a gantry's twin follows the machine an engine watches. The engine is a fake
// client that answers one reading, then waits as the engine's wait does until the page lets go.

Object.assign(globalThis, { React });
beforeEach(() => {
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

const I = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1];
const slide = (label: string, links: [number, number], limits: [number, number]) =>
  ({ label, type: 'prismatic', links, frames: [I, I], limits: [limits], units: ['mm'] });
const gantry = {
  schema: 'cadgen.kinematics/2', name: 'router', ground: 0, loop: null,
  links: [{ name: 'bed', instances: [0], matrix: I }, { name: 'gantry', instances: [1], matrix: I },
    { name: 'carriage', instances: [2], matrix: I }, { name: 'spindle', instances: [3], matrix: I }],
  pairs: [slide('y', [0, 1], [0, 800]), slide('x', [1, 2], [0, 800]), slide('z', [2, 3], [-100, 0])],
  asBuilt: { x: 0, y: 0, z: 0 }, configurations: {},
};
const hinge = { ...gantry, links: gantry.links.slice(0, 2), pairs: [{ ...slide('hinge', [0, 1], [-90, 90]), type: 'revolute', units: ['deg'] }],
  asBuilt: { hinge: 0 } };

function fakeClient(reading: object) {
  const client = {
    watchMachine: vi.fn(async (address: string) => ({ id: 'w1', address, version: 0, connected: false, reading: null, error: null })),
    machine: vi.fn((id: string, { after, signal }: { after: number, signal: AbortSignal }) => {
      if (after < 1) return Promise.resolve({ id, address: 'grbl://mill:23', protocol: 'grbl', version: 1, connected: true, error: null, reading });
      return new Promise((_, reject) => signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))));
    }),
    unwatchMachine: vi.fn(async () => {}),
  };
  return client;
}

function Twin({ kinematics, client, onPose }: { kinematics: any, client: any, onPose: (values: any) => void }) {
  const pose = useXbfPose(kinematics);
  const machine = useMachineMirror({ client, kinematics, values: pose.values, onValues: pose.setValues });
  onPose(pose.values);
  return <FlatPanel mode="docked" open onClose={() => {}} label="Model panel" searchLabel="Search the model" tab="position"
    onTabChange={() => {}} width={240} maxWidth={480} onWidthChange={() => {}} focusSearch={0}
    sections={<XbfPositionSection kinematics={kinematics} machine={machine} values={pose.values} couplings={pose.couplings}
      preset={pose.preset} onValues={pose.setValues} onPreset={pose.choosePreset} onReset={pose.reset} />} />;
}

it('a watched machine poses each axis on its joint, one past its travel at the limit, and the joints take no edit while it does', async () => {
  const client = fakeClient({ axes: { X: 812, Y: 40, Z: -12, B: 5 }, state: 'running', detail: 'Run', feed: 2400, spindle: 18000,
    line: 42, program: null, assumed: ['GRBL reports in millimetres or inches by its $13 setting.'] });
  let values: any = null;
  render(<Twin kinematics={gantry} client={client} onPose={next => { values = next; }} />);
  const address = screen.getByLabelText('Machine address') as HTMLInputElement;
  const watch = screen.getByLabelText('Watch machine') as HTMLButtonElement;
  expect(watch.disabled).toBe(true);
  fireEvent.change(address, { target: { value: 'grbl://mill' } });
  fireEvent.click(watch);
  await waitFor(() => expect(values).toEqual({ y: [40], x: [800], z: [-12] }));
  expect(client.watchMachine).toHaveBeenCalledWith('grbl://mill', expect.anything());
  expect(address.readOnly).toBe(true);
  const text = document.querySelector('[data-machine-row]')!.textContent;
  for (const said of ['Running · line 42 · 2400 mm/min · 18000 rpm', 'GRBL reports in millimetres', 'No joint for axis B',
    "Axis X is past its joint's limits"]) expect(text).toContain(said);
  for (const slider of document.querySelectorAll('[role=slider]')) expect(slider.getAttribute('aria-disabled') ?? slider.getAttribute('data-disabled')).not.toBeNull();
  await act(async () => { fireEvent.click(screen.getByLabelText('Stop watching')); });
  expect(client.unwatchMachine).toHaveBeenCalledWith('w1');
  expect((screen.getByLabelText('Machine address') as HTMLInputElement).readOnly).toBe(false);
  expect(values).toEqual({ x: [800], y: [40], z: [-12] }, 'the twin stays where the machine last was');
});

it('a mechanism with no joint named for an axis has no Machine row', () => {
  render(<Twin kinematics={hinge} client={fakeClient({ axes: {} })} onPose={() => {}} />);
  expect(document.querySelector('[data-machine-row]')).toBeNull();
});
