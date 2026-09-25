import type { ClipboardPort } from '@hardcore/ui/host';
import { copyImageBlobToClipboard, copyTextToClipboard, readTextFromClipboard } from './browserClipboard.js';

export function browserClipboardSupportsImages(): boolean {
  return typeof globalThis.navigator?.clipboard?.write === 'function' && typeof ClipboardItem === 'function';
}

/** Start write during the gesture; deferred PNG encoding stays inside ClipboardItem. */
function writeContent({ text, image }: { text?: string; image?: Blob | Promise<Blob> }): Promise<void> {
  if (image === undefined) return copyTextToClipboard(text ?? '');
  if (text === undefined) return copyImageBlobToClipboard(image).then(() => {});
  const clipboard = navigator.clipboard;
  if (!clipboard?.write || typeof ClipboardItem !== 'function') return Promise.reject(new Error('This browser cannot copy text and an image together. Copy them separately.'));
  const png = Promise.resolve(image).then(blob => {
    if (blob.type !== 'image/png') throw new Error('Prompt image must be a PNG.');
    return blob;
  });
  try {
    const item = new ClipboardItem({ 'text/plain': new Blob([text], { type: 'text/plain' }), 'image/png': png });
    const written = clipboard.write([item]);
    return written.catch(error => { void png.catch(() => {}); throw error; });
  } catch (error) { void png.catch(() => {}); return Promise.reject(error); }
}

export const browserClipboard: ClipboardPort = {
  writeText: copyTextToClipboard,
  readText: readTextFromClipboard,
  async writeImage(image) {
    const png = await image;
    if (png.type !== 'image/png') throw new Error('Screenshot must be a PNG.');
    const response = await fetch('/__cad/clipboard', { method: 'POST', headers: { 'x-cadgen-viewer': '1', 'content-type': 'image/png' }, body: png });
    if (!response.ok) {
      const detail = await response.json().catch(() => null);
      throw new Error(detail?.error || 'Could not copy screenshot to the local clipboard.');
    }
  },
  get writeContent() { return browserClipboardSupportsImages() ? writeContent : undefined; },
};
