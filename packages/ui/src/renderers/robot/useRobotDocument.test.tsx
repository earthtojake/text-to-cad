import { cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { createHttpCadResourceProvider } from '@hardcore/core/client';
import { useRobotDocument } from '../../../dist/renderers/robot/useRobotDocument.js';

const triangle = `solid test
facet normal 0 0 1
outer loop
vertex 0 0 0
vertex 1 0 0
vertex 0 1 0
endloop
endfacet
endsolid test`;
const urdf = (mesh: string) => `<robot name="warm"><link name="base"><visual><geometry><mesh filename="${mesh}"/></geometry></visual></link></robot>`;
const entry = (name: string, kind = 'urdf', extra = {}) => ({ file: `${name}.${kind}`, kind, hash: name, url: `https://robot-assets.test/${name}.${kind}`, ...extra });

afterEach(() => { cleanup(); vi.unstubAllGlobals(); });

it('loads a description and every mesh it names, counting them, and publishes the robot once, whole', async () => {
  // The link mesh arrives when the test says so: each stage is then on screen to be read, not raced.
  let deliverMesh = () => {};
  const meshArrives = new Promise<void>((resolve) => { deliverMesh = resolve; });
  const fetch = vi.fn(async (url: string) => {
    if (!url.endsWith('.stl')) return new Response(urdf('cold-link.stl'));
    await meshArrives;
    return new Response(triangle);
  });
  vi.stubGlobal('fetch', fetch);
  const resources = createHttpCadResourceProvider();
  const hook = renderHook(() => useRobotDocument({ entry: entry('cold'), resources }));
  expect(hook.result.current).toMatchObject({ robot: null, busy: true, progress: { label: 'Loading URDF', determinate: false } });
  await waitFor(() => expect(hook.result.current.progress).toMatchObject({ label: 'Loading meshes', done: 0, total: 1, determinate: true }));
  expect(hook.result.current.robot).toBeNull();
  deliverMesh();
  await waitFor(() => expect(hook.result.current.robot).not.toBeNull());
  expect(hook.result.current).toMatchObject({ busy: false, progress: null, error: null });
  expect(hook.result.current.robot).toMatchObject({ file: 'cold.urdf', kind: 'urdf', revision: 'cold' });
  expect(hook.result.current.robot.parts.map((part: any) => [part.id, part.linkName, part.fillIndex])).toEqual([['base:v1', 'base', 0]]);
  expect(fetch).toHaveBeenCalledTimes(2);
});

it('restores a complete cached robot on the first render, before any loading effect runs', async () => {
  const robot = entry('warm-robot');
  const fetch = vi.fn(async (url: string) => new Response(url.endsWith('.stl') ? triangle : urdf('warm-robot-link.stl')));
  vi.stubGlobal('fetch', fetch);
  const resources = createHttpCadResourceProvider();
  const first = renderHook(() => useRobotDocument({ entry: robot, resources }));
  await waitFor(() => expect(first.result.current.robot).not.toBeNull());
  const { description } = first.result.current.robot;
  first.unmount();
  const reopen = renderHook(() => useRobotDocument({ entry: robot, resources }));
  expect(reopen.result.current.robot.description).toBe(description);
  expect(reopen.result.current).toMatchObject({ busy: false, progress: null });
  expect(fetch).toHaveBeenCalledTimes(2);
});

it('keeps the robot on screen while a new revision loads, and replaces it when that is whole', async () => {
  const fetch = vi.fn(async (url: string) => new Response(url.endsWith('.stl') ? triangle : urdf('live-link.stl')));
  vi.stubGlobal('fetch', fetch);
  const resources = createHttpCadResourceProvider();
  const hook = renderHook(({ current }) => useRobotDocument({ entry: current, resources }), { initialProps: { current: entry('live') } });
  await waitFor(() => expect(hook.result.current.robot).not.toBeNull());
  const before = hook.result.current.robot;
  hook.rerender({ current: entry('live', 'urdf', { hash: 'live-2', url: 'https://robot-assets.test/live.urdf?v=2' }) });
  expect(hook.result.current.robot).toBe(before);
  await waitFor(() => expect(hook.result.current.robot.revision).toBe('live-2'));
  expect(hook.result.current.busy).toBe(false);
});

it('a link mesh that cannot be fetched fails the robot, and an SRDF with no URDF paired says what was looked for', async () => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => (url.endsWith('.stl') ? new Response('', { status: 404, statusText: 'Not Found' }) : new Response(urdf('absent.stl')))));
  const resources = createHttpCadResourceProvider();
  const gone = renderHook(() => useRobotDocument({ entry: entry('gone'), resources }));
  await waitFor(() => expect(gone.result.current.error).not.toBeNull());
  expect(gone.result.current).toMatchObject({ robot: null, busy: false });
  expect(String(gone.result.current.error.message)).toMatch(/absent\.stl.*404/);
  gone.unmount();

  vi.stubGlobal('fetch', vi.fn(async () => new Response('<robot name="nobody"><group name="arm"/></robot>')));
  // (A provider keeps the fetch it was made with.)
  const srdfResources = createHttpCadResourceProvider();
  const lonely = renderHook(() => useRobotDocument({ entry: entry('robots/lonely', 'srdf'), resources: srdfResources }));
  await waitFor(() => expect(lonely.result.current.error).not.toBeNull());
  expect(lonely.result.current.busy).toBe(false);
  expect(lonely.result.current.error.alert.title).toBe('No URDF beside this SRDF');
  expect(lonely.result.current.error.alert.message).toContain('in “robots” for exactly one .urdf file whose <robot name> is “nobody”');
  expect(lonely.result.current.error.message).toContain('robots/lonely.srdf');
});
