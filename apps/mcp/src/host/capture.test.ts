import { afterEach, describe, expect, it, vi } from 'vitest';
import { fitCapture } from './capture';
import { TUNNEL_REPLY_MAX_BYTES } from './tunnel';

describe("a view's picture for the agent", () => {
  afterEach(() => { vi.unstubAllGlobals(); });

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
