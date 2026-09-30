import type { LibraryModel, ModelLibrarySource } from '@text-to-cad/ui/library';

/** A model in this Viewer's library, with the `file` its catalog and `?file=` name it by. */
export interface WebModel extends LibraryModel { file: string }

const CHANGE_HEADERS = { 'x-cadgen-viewer': '1', 'content-type': 'application/json' };

async function library(response: Response): Promise<readonly WebModel[]> {
  const body = await response.json().catch(() => null) as { recents?: WebModel[]; error?: string } | null;
  if (!response.ok || !body?.recents) throw new Error(body?.error || 'The model library could not be read.');
  return body.recents;
}

function change(body: { action: string; file: string; png?: string }): Promise<readonly WebModel[]> {
  return fetch('/__cad/recents', { method: 'POST', headers: CHANGE_HEADERS, body: JSON.stringify(body) }).then(library);
}

/**
 * The library every CAD view shares, as this Viewer shows it: the models under the folder it
 * serves. They open in place, beside the files; there is no chooser to pick one from disk.
 */
export function createWebLibrary({ open }: { open(file: string): void }): ModelLibrarySource<WebModel> {
  return {
    list: () => fetch('/__cad/recents', { cache: 'no-store' }).then(library),
    change: (action, model) => change({ action, file: model.file }),
    thumbnail: async name => `/__cad/recents/thumbnail?name=${encodeURIComponent(name)}`,
    open: async model => open(model.file),
  };
}

/** The file on screen joins the library. */
export const recordOpened = (file: string) => change({ action: 'open', file });

/** Its picture, for the library's cards. */
export async function recordThumbnail(file: string, png: Blob) {
  const bytes = new Uint8Array(await png.arrayBuffer());
  let binary = '';
  for (let index = 0; index < bytes.length; index += 0x8000) binary += String.fromCharCode(...bytes.subarray(index, index + 0x8000));
  return change({ action: 'thumbnail', file, png: btoa(binary) });
}
