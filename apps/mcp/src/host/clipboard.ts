import type { ClipboardPort } from '@text-to-cad/ui/host';

/**
 * The page's own clipboard. The host grants its frame clipboard writes (the resource asks for
 * `clipboardWrite`); reading is the host's to allow and may be refused.
 */
export const frameClipboard: ClipboardPort = {
  async writeText(text) {
    if (typeof text === 'string') {
      if (!navigator.clipboard?.writeText) throw new Error('Copying is not available here.');
      await navigator.clipboard.writeText(text);
      return;
    }
    // Still on its way: the write starts now, in the gesture, and takes the text when it arrives.
    if (!navigator.clipboard?.write || typeof ClipboardItem !== 'function') throw new Error('Copying is not available here.');
    const blob = text.then(value => new Blob([value], { type: 'text/plain' }));
    try { await navigator.clipboard.write([new ClipboardItem({ 'text/plain': blob })]); }
    catch (error) { await blob; throw error; }
  },
  async readText() {
    if (!navigator.clipboard?.readText) throw new Error('Pasting is not available here.');
    return navigator.clipboard.readText();
  },
  async writeImage(image) {
    if (!navigator.clipboard?.write || typeof ClipboardItem !== 'function') throw new Error('Copying images is not available here.');
    const png = Promise.resolve(image).then(blob => {
      if (blob.type !== 'image/png') throw new Error('A copied image is a PNG.');
      return blob;
    });
    try { await navigator.clipboard.write([new ClipboardItem({ 'image/png': png })]); }
    finally { void png.catch(() => {}); }
  },
};
