import { afterEach, describe, expect, it, vi } from 'vitest';
import { captureSettled, fitCapture } from './capture';
import { createLiveRegistry, type LiveController } from './live';
import { TUNNEL_REPLY_MAX_BYTES } from './tunnel';

/** A renderer's live controller showing `path`, loading until told otherwise; each capture is a PNG naming it. */
function view(path: string, { loading = true, fails = '' } = {}) {
  const state = { loading, active: true, resource: { kind: 'workspace-file', path } };
  const controller = {
    readState: () => state,
    capture: vi.fn(async () => { if (fails) throw new Error(fails); return new Blob([path], { type: 'image/png' }); }),
    thumbnail: async () => new Blob(),
  } as unknown as LiveController & { capture: ReturnType<typeof vi.fn> };
  return { controller, loaded() { state.loading = false; } };
}

describe("a view's picture for the agent", () => {
  afterEach(() => { vi.unstubAllGlobals(); });

  it('waits for the model the agent showed to load, rather than failing while it does', async () => {
    const live = createLiveRegistry();
    // The agent showed b.step and captured at once: a.step is still bound and drawn, b.step not yet shown.
    const a = view('/m/a.step', { loading: false });
    live.binding.bind(a.controller);
    const picture = captureSettled(live, () => '/m/b.step', { timeoutMs: 5_000 });
    await new Promise(resolve => setTimeout(resolve, 150));
    const b = view('/m/b.step');
    live.binding.bind(b.controller);
    await new Promise(resolve => setTimeout(resolve, 150));
    expect(b.controller.capture).not.toHaveBeenCalled();
    b.loaded();
    expect(await (await picture).text()).toBe('/m/b.step');
    expect(a.controller.capture).not.toHaveBeenCalled();
  });

  it('matches the file however its path is spelled, and fails at once with no model or a failed capture', async () => {
    const live = createLiveRegistry();
    live.binding.bind(view('C:/Models/a.step', { loading: false }).controller);
    expect(await (await captureSettled(live, () => 'c:\\Models\\a.step', { timeoutMs: 1_000 })).text()).toBe('C:/Models/a.step');
    await expect(captureSettled(live, () => null)).rejects.toThrow('No model is showing');
    live.binding.bind(view('/m/a.step', { loading: false, fails: 'Screenshot capture failed' }).controller);
    const started = Date.now();
    await expect(captureSettled(live, () => '/m/a.step', { timeoutMs: 5_000 })).rejects.toThrow('Screenshot capture failed');
    expect(Date.now() - started).toBeLessThan(1_000);
  });

  it('says the model did not finish loading once its wait is over', async () => {
    const live = createLiveRegistry();
    live.binding.bind(view('/m/a.step').controller);
    await expect(captureSettled(live, () => '/m/a.step', { timeoutMs: 300 })).rejects.toThrow(/did not finish loading.*Capture again/);
  });

  it('goes as it is when it fits in one reply, and is drawn again smaller until it does', async () => {
    const small = new Blob([new Uint8Array(1000)], { type: 'image/png' });
    expect(await fitCapture(small)).toBe(small);
    const drawn: number[][] = [];
    vi.stubGlobal('createImageBitmap', async () => ({ width: 4000, height: 3000, close() {} }));
    vi.stubGlobal('OffscreenCanvas', class {
      constructor(public width: number, public height: number) { drawn.push([width, height]); }
      getContext() { return { drawImage() {} }; }
      // A picture's PNG grows with its pixels: here, a byte a pixel.
      async convertToBlob() { return new Blob([new Uint8Array(this.width * this.height)], { type: 'image/png' }); }
    });
    const fitted = await fitCapture(new Blob([new Uint8Array(4000 * 3000)], { type: 'image/png' }));
    expect(fitted.size).toBeLessThanOrEqual(TUNNEL_REPLY_MAX_BYTES);
    expect(drawn).toHaveLength(1);
  });
});
