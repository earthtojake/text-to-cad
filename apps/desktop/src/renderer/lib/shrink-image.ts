/** The smallest side a shrunk capture may have; below it the picture says nothing. */
const MIN_SIDE = 64;

/**
 * `blob` redrawn at `scale` of its width and height, as a PNG, or null where
 * the page cannot decode or encode images or the result would be a speck.
 * The seam a test replaces: jsdom has no canvas.
 */
export async function shrinkImage(blob: Blob, scale: number): Promise<Blob | null> {
  if (typeof createImageBitmap !== "function" || typeof OffscreenCanvas !== "function") return null;
  const bitmap = await createImageBitmap(blob);
  try {
    const width = Math.round(bitmap.width * scale);
    const height = Math.round(bitmap.height * scale);
    if (Math.min(width, height) < MIN_SIDE) return null;
    const canvas = new OffscreenCanvas(width, height);
    const context = canvas.getContext("2d");
    if (!context) return null;
    context.drawImage(bitmap, 0, 0, width, height);
    return await canvas.convertToBlob({ type: "image/png" });
  } finally {
    bitmap.close();
  }
}
