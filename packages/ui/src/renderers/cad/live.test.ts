import { describe, expect, it, vi } from 'vitest';
import { attachCadLiveBinding } from './live';
import type { CadLiveController, CadLiveState } from './live';

const state = (): Omit<CadLiveState, 'active'> => ({
  resource: { kind: 'workspace-file', workspaceId: 'root', path: 'model.step', revision: 'r1' },
  revision: 'r1', loading: false, selection: [], selectedPartIds: [], selectedReferenceIds: [],
  hiddenPartIds: [], isolatedPartIds: [], camera: null, display: { mode: 'shaded_edges' }, renderMode: 'inspect',
});
function harness(settle = () => Promise.resolve()) {
  let current = state();
  let controller!: CadLiveController;
  const commands = { select: vi.fn(), clearSelection: vi.fn(), setCamera: vi.fn(), resetCamera: vi.fn(),
    setDisplaySettings: vi.fn(), setRenderMode: vi.fn(), capture: vi.fn(() => Promise.resolve(new Blob(['png']))) };
  const release = vi.fn();
  const readRuntime = vi.fn(() => ({ ...commands, readState: () => current }));
  const detach = attachCadLiveBinding({ bind(value) { controller = value; return release; } }, readRuntime, settle);
  return { controller, commands, detach, release, readRuntime, update: (next: typeof current) => { current = next; } };
}

describe('live CAD viewer binding', () => {
  it('routes camera, clear, display and mode commands and returns the committed actual frame', async () => {
    const view = harness();
    const camera = { position: [4, 5, 6], target: [0, 0, 0], up: [0, 0, 1] } as const;
    view.commands.setCamera.mockImplementation(snapshot => view.update({ ...state(), camera: snapshot }));
    expect((await view.controller.setCamera({ ...camera, position: [...camera.position], target: [...camera.target], up: [...camera.up] })).camera?.position).toEqual([4, 5, 6]);
    await view.controller.resetCamera(); expect(view.commands.resetCamera).toHaveBeenCalledOnce();
    view.commands.clearSelection.mockImplementation(() => view.update(state()));
    expect((await view.controller.clearSelection()).selection).toEqual([]);
    await view.controller.setDisplaySettings({ mode: 'wire' }); expect(view.commands.setDisplaySettings).toHaveBeenCalledWith({ mode: 'wire' });
    view.commands.setRenderMode.mockImplementation(enabled => view.update({ ...state(), renderMode: enabled ? 'render' : 'inspect' }));
    expect((await view.controller.setRenderMode(true)).renderMode).toBe('render');
    expect((await view.controller.setRenderMode(false)).renderMode).toBe('inspect');
  });
  it('reads the actual latest view and returns detached pure snapshots', async () => {
    const view = harness();
    view.update({ ...state(), selectedReferenceIds: ['f1'], camera: { position: [1, 2, 3], target: [0, 0, 0], up: [0, 0, 1] } });
    const snapshot = view.controller.readState();
    expect(snapshot).toMatchObject({ active: true, selectedReferenceIds: ['f1'], revision: 'r1' });
    (snapshot.selectedReferenceIds as string[]).push('f2');
    expect(view.controller.readState().selectedReferenceIds).toEqual(['f1']);
    await view.controller.select({ selectors: ['f1'], replace: false });
    expect(view.commands.select).toHaveBeenCalledWith({ selectors: ['f1'], replace: false });
  });
  it('waits for a lazy render-mode commit instead of returning its predecessor state', async () => {
    let frames = 0;
    const view = harness(async () => {
      if (++frames === 3) view.update({ ...state(), renderMode: 'render' });
    });
    expect((await view.controller.setRenderMode(true)).renderMode).toBe('render');
    expect(frames).toBe(3);
    expect(view.commands.setRenderMode).toHaveBeenCalledExactlyOnceWith(true);
  });
  it('bounds a render-mode command that never commits', async () => {
    const now = vi.spyOn(Date, 'now').mockReturnValueOnce(0).mockReturnValue(10_001);
    try { await expect(harness().controller.setRenderMode(true)).rejects.toThrow('did not finish'); }
    finally { now.mockRestore(); }
  });
  it('retains an inactive final state while rejecting controls and releasing the mounted runtime', async () => {
    const view = harness();
    view.detach();
    const reads = view.readRuntime.mock.calls.length;
    view.update({ ...state(), revision: 'r2' });
    expect(view.controller.readState()).toMatchObject({ active: false, revision: 'r1' });
    await expect(view.controller.clearSelection()).rejects.toThrow('Show the model tab');
    await expect(view.controller.capture()).rejects.toThrow('Show the model tab');
    expect(view.readRuntime).toHaveBeenCalledTimes(reads);
    expect(view.commands.capture).not.toHaveBeenCalled();
    view.detach();
    expect(view.release).toHaveBeenCalledTimes(1);
  });
  it('refuses loading views and rejects a command whose displayed revision changes before commit', async () => {
    let finish!: () => void;
    const view = harness(() => new Promise<void>(resolve => { finish = resolve; }));
    view.update({ ...state(), loading: true });
    await expect(view.controller.resetCamera()).rejects.toThrow('finish loading');
    expect(view.commands.resetCamera).not.toHaveBeenCalled();
    view.update(state());
    const pending = view.controller.setRenderMode(true);
    view.update({ ...state(), revision: 'r2' });
    finish();
    await expect(pending).rejects.toThrow('revision changed');
  });
  it('rejects a capture from a departed or replaced viewport', async () => {
    let encode!: (blob: Blob) => void;
    const view = harness();
    view.commands.capture.mockImplementation(() => new Promise<Blob>(resolve => { encode = resolve; }));
    const pending = view.controller.capture();
    view.detach();
    encode(new Blob(['png']));
    await expect(pending).rejects.toThrow('tab closed');
  });
  it('rejects capture after resource identity changes even when the revision token is equal', async () => {
    let encode!: (blob: Blob) => void;
    const view = harness();
    view.commands.capture.mockImplementation(() => new Promise<Blob>(resolve => { encode = resolve; }));
    const pending = view.controller.capture();
    view.update({ ...state(), resource: { kind: 'workspace-file', workspaceId: 'root', path: 'other.step', revision: 'r1' } });
    encode(new Blob(['png']));
    await expect(pending).rejects.toThrow('revision changed');
  });
});
