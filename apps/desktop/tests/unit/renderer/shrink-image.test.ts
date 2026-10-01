/**
 * The real `shrinkImage` loop under `imageResult`, with the page's image APIs
 * stubbed (jsdom has none): a bitmap knows the size of the blob it decoded,
 * and a canvas encodes to whatever `encodedBytes` says for its area.
 */
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { imageResult } from "@renderer/state/image-result";
import { shrinkImage } from "@renderer/lib/shrink-image";
import { MAX_IMAGE_BYTES } from "@shared/image-cap";

const sizes = new WeakMap<Blob, { width: number; height: number }>();
const canvases: Array<{ width: number; height: number }> = [];
let bitmaps = 0;
let encodedBytes: (area: number) => number;

/** A blob with a real PNG signature and IHDR, padded to `bytes`, that the stub decodes at width x height. */
function png(width: number, height: number, bytes: number): Blob {
  const head = new Uint8Array(24);
  const view = new DataView(head.buffer);
  view.setUint32(0, 0x89504e47); view.setUint32(4, 0x0d0a1a0a); view.setUint32(8, 13); view.setUint32(12, 0x49484452);
  view.setUint32(16, width); view.setUint32(20, height);
  const blob = new Blob([head, new Uint8Array(Math.max(0, bytes - 24))], { type: "image/png" });
  sizes.set(blob, { width, height });
  return blob;
}

beforeEach(() => {
  canvases.length = 0; bitmaps = 0;
  encodedBytes = (area) => area / 2; // proportional to area
  vi.stubGlobal("createImageBitmap", async (blob: Blob) => { bitmaps += 1; return { ...sizes.get(blob)!, close: () => {} }; });
  vi.stubGlobal("OffscreenCanvas", class {
    constructor(readonly width: number, readonly height: number) { canvases.push({ width, height }); }
    getContext() { return { drawImage: () => {} }; }
    async convertToBlob() { return png(this.width, this.height, encodedBytes(this.width * this.height)); }
  });
});
afterEach(() => { vi.unstubAllGlobals(); });

it("one pass brings a proportional 8 MiB capture under the limit, at a scale of at most 0.75, and says where it came from", async () => {
  const result = await imageResult(png(4096, 4096, 8 * 1024 * 1024), { tabId: "t" });
  expect(bitmaps).toBe(1);
  expect(canvases).toHaveLength(1);
  expect(canvases[0]!.width / 4096).toBeLessThanOrEqual(0.75);
  expect(result).toMatchObject({ tabId: "t", scaled: true, scaledFrom: { width: 4096, height: 4096 } });
  expect(result.scale).toBeCloseTo(canvases[0]!.width / 4096, 2);
  expect(result.base64.length * 3 / 4).toBeLessThan(MAX_IMAGE_BYTES);
});

it("a capture just over the limit steps by 0.75, never by less", async () => {
  await imageResult(png(4000, 2000, Math.ceil(MAX_IMAGE_BYTES * 1.01)), {});
  expect(canvases).toEqual([{ width: 3000, height: 1500 }]);
});

it("gives up after six passes when the encoding never gets smaller, and attaches nothing", async () => {
  encodedBytes = () => MAX_IMAGE_BYTES * 2;
  await expect(imageResult(png(4096, 4096, MAX_IMAGE_BYTES * 2), {})).rejects.toThrow(/could not be scaled under the model's image limit/);
  expect(bitmaps).toBe(6);
});

it("refuses to redraw a capture whose short side would fall under 64 px", async () => {
  expect(await shrinkImage(png(100, 100, 10), 0.5)).toBeNull();
  expect(canvases).toHaveLength(0);
  expect(await shrinkImage(png(100, 100, 10), 0.7)).not.toBeNull();
  // Through imageResult the floor is a refusal, not a speck.
  await expect(imageResult(png(100, 80, MAX_IMAGE_BYTES * 2), {})).rejects.toThrow(/could not be scaled/);
  expect(canvases).toHaveLength(1); // only the direct 0.7 call above drew
});

it("a capture under the limit is untouched and carries no scale", async () => {
  const result = await imageResult(png(800, 600, 1024), {});
  expect(bitmaps).toBe(0);
  expect(result).not.toHaveProperty("scaled");
  expect(result).not.toHaveProperty("scaledFrom");
});
