import { describe, expect, it, vi } from 'vitest';
import { attachLiveBinding, HOST_LIVE_COMMANDS } from './liveBinding';
import type { LiveViewController, LiveViewState } from './liveBinding';

const state = (): Omit<LiveViewState, 'active'> => ({
  resource: { kind: 'workspace-file', workspaceId: 'root', path: 'scene.glb', revision: 'r1' },
  revision: 'r1', loading: false, selection: [], camera: null, display: { mode: 'solid' }, renderMode: 'inspect',
});
function harness(options: Parameters<typeof attachLiveBinding>[2], extra: Record<string, unknown> = {}) {
  let controller!: LiveViewController & Record<string, (...args: unknown[]) => Promise<unknown>>;
  const runtime = { readState: state, setCamera: vi.fn(), resetCamera: vi.fn(), setDisplaySettings: vi.fn(), setRenderMode: vi.fn(),
    capture: vi.fn(() => Promise.resolve(new Blob(['png']))), ...extra };
  const detach = attachLiveBinding({ bind(value) { controller = value as typeof controller; return () => {}; } }, () => runtime,
    { settle: () => Promise.resolve(), ...options });
  return { controller, runtime, detach };
}
const declined = { select: 'This view has nothing to select.', clearSelection: 'This view has no selection.' };

describe('the shell live binding', () => {
  it('declines a host command with the renderer\'s own sentence, never silently', async () => {
    const view = harness({ declined });
    await expect(view.controller.select({ selectors: ['f1'] })).rejects.toThrow('This view has nothing to select.');
    await expect(view.controller.clearSelection()).rejects.toThrow('This view has no selection.');
    await view.controller.resetCamera();
    expect(view.runtime.resetCamera).toHaveBeenCalledOnce();
  });
  it('adds a renderer\'s own commands as admitted mutations that return the committed state', async () => {
    const select = vi.fn(), clearSelection = vi.fn(), setJoint = vi.fn();
    const view = harness({ commands: ['select', 'clearSelection', 'setJoint'] }, { select, clearSelection, setJoint });
    expect(await view.controller.setJoint('elbow', 0.5)).toMatchObject({ active: true, revision: 'r1' });
    expect(setJoint).toHaveBeenCalledWith('elbow', 0.5);
    view.detach();
    await expect(view.controller.setJoint('elbow', 1)).rejects.toThrow('Show the model tab');
  });
  it('refuses a renderer that neither implements nor declines a known host command', () => {
    expect(HOST_LIVE_COMMANDS).toEqual(['select', 'clearSelection']);
    expect(() => harness({ declined: { select: 'no' } })).toThrow('must either implement or decline the host command "clearSelection"');
    expect(() => harness({ commands: ['select', 'clearSelection'], declined: { select: 'no' } })).toThrow('"select"');
    expect(() => harness({ commands: ['select', 'clearSelection', 'capture'] })).toThrow('already part of every renderer');
  });
  it('fails loudly when a declared command is missing from the mounted view', async () => {
    const view = harness({ commands: ['select', 'clearSelection'] }, { select: vi.fn() });
    await expect(view.controller.clearSelection()).rejects.toThrow('declared the live command "clearSelection"');
  });
  it('answers a render-mode switch once the viewport shows the mode, not once the store names it', async () => {
    // The store flips at once; the camera takes the mode's projection some frames later.
    let mode = 'solid', projection: 'orthographic' | 'perspective' = 'orthographic', frames = 0;
    const camera = () => ({ position: [1, 1, 1] as [number, number, number], target: [0, 0, 0] as [number, number, number], up: [0, 0, 1] as [number, number, number], projection });
    const view = harness({ declined, settle: async () => {
      frames += 1;
      if (frames === 3) projection = mode === 'render' ? 'perspective' : 'orthographic';
    } }, {
      readState: () => ({ ...state(), camera: camera(), display: { mode }, renderMode: mode === 'render' ? 'render' : 'inspect' }),
      setRenderMode: (enabled: boolean) => { mode = enabled ? 'render' : 'solid'; frames = 0; },
    });
    expect((await view.controller.setRenderMode(true)).camera?.projection).toBe('perspective');
    expect(frames).toBe(3);
    expect((await view.controller.setRenderMode(false)).camera?.projection).toBe('orthographic');
  });
});
