import { MAX_IMAGE_BYTES } from "@shared/image-cap";
import { shrinkImage } from "../lib/shrink-image";

// Each pass at least halves the area of a still-too-large PNG, and a photo-like
// drawing that needs more than this is not going to fit at a size worth seeing.
const MAX_PASSES = 6;

/** A PNG's pixel size from its IHDR (bytes 16-24 after the signature), or null for anything else. */
async function pngSize(blob: Blob): Promise<{ width: number; height: number } | null> {
  const head = new DataView(await blob.slice(0, 24).arrayBuffer());
  if (head.byteLength < 24 || head.getUint32(0) !== 0x89504e47 || head.getUint32(12) !== 0x49484452) return null;
  return { width: head.getUint32(16), height: head.getUint32(20) };
}

/**
 * A capture as the tool result the agent gets: base64 and its type, with
 * `scaled: true` when it had to be redrawn smaller to stay under the model's
 * image limit. Then `scale` is how much each side shrank and `scaledFrom` the
 * original pixel size (when the source is a PNG that says so), so an agent can
 * map a point read off the picture back to the capture's own pixels. A pasted
 * raster in a drawing, or a large viewer, can encode to far more than the
 * model takes; refusing here says so instead of poisoning the transcript with
 * a result it rejects.
 */
export async function imageResult(source: Blob, metadata: Record<string, unknown>) {
  let blob = source;
  let scale = 1;
  for (let pass = 0; blob.size > MAX_IMAGE_BYTES && pass < MAX_PASSES; pass += 1) {
    // Encoded size tracks area, so the side scales with its square root; the
    // 0.9 leaves room for the estimate being optimistic.
    const step = Math.min(0.75, Math.sqrt(MAX_IMAGE_BYTES / blob.size) * 0.9);
    const smaller = await shrinkImage(blob, step);
    if (!smaller) break;
    blob = smaller; scale *= step;
  }
  if (blob.size > MAX_IMAGE_BYTES) throw new Error(`The capture is ${(source.size / 1024 / 1024).toFixed(1)} MB and could not be scaled under the model's image limit (about ${(MAX_IMAGE_BYTES / 1024 / 1024).toFixed(2)} MB of file); nothing was attached.`);
  const from = scale < 1 ? await pngSize(source) : null;
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = ""; for (let at = 0; at < bytes.length; at += 0x8000) binary += String.fromCharCode(...bytes.subarray(at, at + 0x8000));
  return { ...metadata, mimeType: blob.type, base64: btoa(binary), ...(scale < 1 ? { scaled: true, scale, ...(from ? { scaledFrom: from } : {}) } : {}) };
}
