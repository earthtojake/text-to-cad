import type { LibraryModel } from '@text-to-cad/ui/library';

/**
 * The library every CAD view shares, as this Viewer reaches it: the home lists it, pins and
 * removes its models and draws their pictures, and Open picks a model with the desktop's own
 * chooser; a model on screen joins it with its picture. Models are named by absolute path.
 */

const CHANGE_HEADERS = { 'x-cadgen-viewer': '1', 'content-type': 'application/json' };

async function answer<T>(response: Response, failure: string): Promise<T> {
  const body = await response.json().catch(() => null) as (T & { error?: string }) | null;
  if (!response.ok || !body) throw new Error(body?.error || failure);
  return body;
}

/** The models opened before, newest first. */
export async function listRecents(): Promise<LibraryModel[]> {
  const response = await fetch('/__cad/recents', { cache: 'no-store' });
  return (await answer<{ recents: LibraryModel[] }>(response, 'The model library could not be read.')).recents;
}

/** A change to the library: the list as it stands after it. */
export async function changeRecents(body: { action: 'open' | 'pin' | 'unpin' | 'remove' | 'thumbnail'; path: string; png?: string }): Promise<LibraryModel[]> {
  const response = await fetch('/__cad/recents', { method: 'POST', headers: CHANGE_HEADERS, body: JSON.stringify(body) });
  return (await answer<{ recents: LibraryModel[] }>(response, 'The model library could not be written.')).recents;
}

/** The file on screen joins the library. */
export const recordOpened = (path: string) => changeRecents({ action: 'open', path }).then(() => {});

/** Its picture, for the library's cards. */
export async function recordThumbnail(png: Blob, path: string) {
  const bytes = new Uint8Array(await png.arrayBuffer());
  let binary = '';
  for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  return changeRecents({ action: 'thumbnail', path, png: btoa(binary) });
}

/** A card's picture, by the name the library gives it. */
export const thumbnailUrl = (name: string) => `/__cad/thumbnail?name=${encodeURIComponent(name)}`;

/** Open: the model the person picks with the desktop's chooser, or null when they cancel. */
export async function pickModel(): Promise<string | null> {
  const response = await fetch('/__cad/pick', { method: 'POST', headers: CHANGE_HEADERS });
  const picked = await answer<{ path?: string; cancelled?: boolean }>(response, 'The file chooser could not open.');
  return picked.path ?? null;
}
