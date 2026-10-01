/**
 * The library every CAD view shares, as this Viewer takes part in it: it records the models it
 * opens and their pictures, for the views that show the library (the Codex sidebar's home). The
 * Viewer has no home of its own, so it never reads the library.
 */

const CHANGE_HEADERS = { 'x-cadgen-viewer': '1', 'content-type': 'application/json' };

async function change(body: { action: 'open' | 'thumbnail'; file: string; png?: string }): Promise<void> {
  const response = await fetch('/__cad/recents', { method: 'POST', headers: CHANGE_HEADERS, body: JSON.stringify(body) });
  if (!response.ok) {
    const failure = await response.json().catch(() => null) as { error?: string } | null;
    throw new Error(failure?.error || 'The model library could not be written.');
  }
}

/** The file on screen joins the library. */
export const recordOpened = (file: string) => change({ action: 'open', file });

/** Its picture, for the library's cards. */
export async function recordThumbnail(png: Blob, file: string) {
  const bytes = new Uint8Array(await png.arrayBuffer());
  let binary = '';
  for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  return change({ action: 'thumbnail', file, png: btoa(binary) });
}
