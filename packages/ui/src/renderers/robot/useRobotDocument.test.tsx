import { cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createHttpCadResourceProvider } from '@text-to-cad/core/client';
import { useRobotDocument } from '../../../dist/renderers/robot/useRobotDocument.js';
import { fixtureGlb as glb, fixturePayload, fixtureRefusal } from './__tests__/robotFixtures.js';

// The hook over cadgen's answer for a description (`GET /__cad/robot`, here a client whose `robot`
// is a stub) and the meshes that answer names, fetched as the page fetches them.
const entry = (name: string, extra = {}) => ({ file: `/models/${name}`, kind: name.split('.').pop(), hash: name, url: `https://robot-assets.test/${name}`, ...extra });
const client = (answer: (file: string) => unknown) => ({ robot: vi.fn(async (file: string) => answer(file)) });
const swing = () => fixturePayload('swing.sdf');

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('reads the payload, then every mesh it names, counting them, and publishes the robot once, whole', async () => {
  // The meshes arrive when the test says so: each stage is then on screen to be read, not raced.
  let deliverMeshes = () => {};
  const meshesArrive = new Promise<void>((resolve) => { deliverMeshes = resolve; });
  const fetch = vi.fn(async (url: string) => { await meshesArrive; return new Response(glb(url)); });
  vi.stubGlobal('fetch', fetch);
  const resources = createHttpCadResourceProvider();
  const robot = client(() => swing());
  const hook = renderHook(() => useRobotDocument({ entry: entry('swing.sdf'), client: robot, resources }));
  expect(hook.result.current).toMatchObject({ robot: null, busy: true, progress: { label: 'Loading SDF', determinate: false } });
  await waitFor(() => expect(hook.result.current.progress).toMatchObject({ label: 'Loading meshes', done: 0, total: 2, determinate: true }));
  expect(hook.result.current.robot).toBeNull();
  deliverMeshes();
  await waitFor(() => expect(hook.result.current.robot).not.toBeNull());
  expect(hook.result.current).toMatchObject({ busy: false, progress: null, error: null });
  expect(hook.result.current.robot).toMatchObject({ file: '/models/swing.sdf', kind: 'sdf', revision: 'swing.sdf' });
  expect(hook.result.current.robot.robot.articulation.controls.map((control: any) => control.id)).toEqual(['hinge']);
  expect(hook.result.current.robot.parts.map((part: any) => [part.id, part.link])).toEqual([['base:v1', 'base'], ['arm:v1', 'arm']]);
  expect(robot.robot).toHaveBeenCalledWith('/models/swing.sdf', expect.anything());
  expect(fetch).toHaveBeenCalledTimes(2);
});

it('restores a complete cached robot on the first render, before any loading effect runs', async () => {
  const fetch = vi.fn(async (url: string) => new Response(glb(url)));
  vi.stubGlobal('fetch', fetch);
  const resources = createHttpCadResourceProvider();
  const warm = entry('swing.sdf', { hash: 'warm-robot', url: 'https://robot-assets.test/warm.sdf' });
  const first = renderHook(() => useRobotDocument({ entry: warm, client: client(() => swing()), resources }));
  await waitFor(() => expect(first.result.current.robot).not.toBeNull());
  const { robot } = first.result.current.robot;
  first.unmount();
  const reopen = renderHook(() => useRobotDocument({ entry: warm, client: client(() => { throw new Error('a warm robot asks nothing'); }), resources }));
  expect(reopen.result.current.robot.robot).toBe(robot);
  expect(reopen.result.current).toMatchObject({ busy: false, progress: null });
  expect(fetch).toHaveBeenCalledTimes(2);
});

it('keeps the robot on screen while a new revision loads, and replaces it when that is whole', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(glb(url))));
  const resources = createHttpCadResourceProvider();
  const live = entry('swing.sdf', { hash: 'live', url: 'https://robot-assets.test/live.sdf' });
  const hook = renderHook(({ current }) => useRobotDocument({ entry: current, client: client(() => swing()), resources }), { initialProps: { current: live } });
  await waitFor(() => expect(hook.result.current.robot).not.toBeNull());
  const before = hook.result.current.robot;
  hook.rerender({ current: { ...live, hash: 'live-2', url: 'https://robot-assets.test/live.sdf?v=2' } });
  expect(hook.result.current.robot).toBe(before);
  await waitFor(() => expect(hook.result.current.robot.revision).toBe('live-2'));
  expect(hook.result.current.busy).toBe(false);
});

it('a mesh that cannot be fetched fails the robot, and an SRDF cadgen could not pair says what it looked for', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response('', { status: 404, statusText: 'Not Found' })));
  const resources = createHttpCadResourceProvider();
  const payload = swing();
  payload.visuals[0].mesh.url = '/meshes/absent.glb';
  const gone = renderHook(() => useRobotDocument({ entry: entry('gone.sdf'), client: client(() => payload), resources }));
  await waitFor(() => expect(gone.result.current.error).not.toBeNull());
  expect(gone.result.current).toMatchObject({ robot: null, busy: false });
  expect(String(gone.result.current.error.message)).toMatch(/absent\.glb.*404/);
  gone.unmount();

  // cadgen refuses a description at the door (`GET /__cad/robot` is a 400 with its sentence): the
  // sentence is the error a person reads, about the file, not a request that failed.
  const refused = fixtureRefusal('gone.urdf');
  const door = client(() => { throw Object.assign(new Error(refused), { failure: { kind: 'http', status: 400, detail: refused, operation: 'robot' } }); });
  const missing = renderHook(() => useRobotDocument({ entry: entry('gone.urdf'), client: door, resources }));
  await waitFor(() => expect(missing.result.current.error).not.toBeNull());
  expect(missing.result.current.error.message).toBe(refused);
  expect(missing.result.current.error.failure).toBeUndefined();
  missing.unmount();

  // An SRDF cadgen could not pair gets the alert that says what was looked for, around cadgen's sentence.
  const refusal = fixtureRefusal('lonely.srdf');
  const lonely = renderHook(() => useRobotDocument({ entry: entry('lonely.srdf'), client: client(() => { throw new Error(refusal); }), resources }));
  await waitFor(() => expect(lonely.result.current.error).not.toBeNull());
  expect(lonely.result.current.busy).toBe(false);
  expect(lonely.result.current.error.alert.title).toBe('No URDF beside this SRDF');
  expect(lonely.result.current.error.alert.message).toContain('in “/models” for exactly one .urdf file with the same <robot name>');
  expect(lonely.result.current.error.alert.message).toContain("no .urdf in /models declares <robot name='nobody'>");
  expect(lonely.result.current.error.message).toContain('/models/lonely.srdf');
});
