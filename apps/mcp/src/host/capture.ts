import { TUNNEL_REPLY_MAX_BYTES } from './tunnel';

/**
 * A view's picture for the agent (`cad_screenshot`), in one message: the server refuses one longer
 * than a reply carries (`TUNNEL_REPLY_MAX_BYTES`), since a host could close the connection on it.
 * A longer PNG is drawn again smaller, by about as much as it is over, until it fits.
 */
export async function fitCapture(png: Blob): Promise<Blob> {
  let fitted = png;
  let scale = 1;
  while (fitted.size > TUNNEL_REPLY_MAX_BYTES && scale > 1 / 64) {
    scale *= 0.9 * Math.sqrt(TUNNEL_REPLY_MAX_BYTES / fitted.size);
    const image = await createImageBitmap(png);
    const canvas = new OffscreenCanvas(Math.max(1, Math.round(image.width * scale)), Math.max(1, Math.round(image.height * scale)));
    canvas.getContext('2d')!.drawImage(image, 0, 0, canvas.width, canvas.height);
    image.close();
    fitted = await canvas.convertToBlob({ type: 'image/png' });
  }
  return fitted;
}
