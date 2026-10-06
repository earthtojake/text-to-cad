import type { ClipboardPort } from '@text-to-cad/ui/host';

/** The page's own clipboard: the browser's. Copying is what the page can do with a prompt. */
export type WebClipboard = ClipboardPort & {
  /** Text and a PNG as two representations of one clipboard item, where the browser can. */
  writeContent?(content: { text?: string; image?: Blob | Promise<Blob> }): Promise<void>;
};

export function clipboardSupportsImages(): boolean {
  return typeof globalThis.navigator?.clipboard?.write === 'function' && typeof ClipboardItem === 'function';
}

function pngOf(image: Blob | Promise<Blob>): Promise<Blob> {
  const png = Promise.resolve(image).then(blob => {
    if (blob.type !== 'image/png') throw new Error('A copied image is a PNG.');
    return blob;
  });
  void png.catch(() => {});
  return png;
}

async function writeContent({ text, image }: { text?: string; image?: Blob | Promise<Blob> }): Promise<void> {
  if (image === undefined) return browserClipboard.writeText(text ?? '');
  if (text === undefined) return browserClipboard.writeImage(image);
  if (!clipboardSupportsImages()) throw new Error('This browser cannot copy text and an image together. Copy them separately.');
  const png = pngOf(image);
  await navigator.clipboard.write([new ClipboardItem({ 'text/plain': new Blob([text], { type: 'text/plain' }), 'image/png': png })]);
}

export const browserClipboard: WebClipboard = {
  async writeText(text) {
    if (typeof text === 'string') {
      if (!navigator.clipboard?.writeText) throw new Error('Copying is not available here.');
      await navigator.clipboard.writeText(text);
      return;
    }
    // Still on its way (a copied Quick Edit whose sketch is being saved): the write starts now,
    // inside the gesture, and takes the text when it arrives; a browser that refuses a pending
    // item gets the text itself, once it has arrived.
    if (navigator.clipboard?.write && typeof ClipboardItem === 'function') {
      const blob = text.then(value => new Blob([String(value ?? '')], { type: 'text/plain' }));
      void blob.catch(() => {});
      try { await navigator.clipboard.write([new ClipboardItem({ 'text/plain': blob })]); return; }
      catch { await blob; }
    }
    if (!navigator.clipboard?.writeText) throw new Error('Copying is not available here.');
    await navigator.clipboard.writeText(String((await text) ?? ''));
  },
  async readText() {
    if (!navigator.clipboard?.readText) throw new Error('Pasting is not available here.');
    return navigator.clipboard.readText();
  },
  async writeImage(image) {
    if (!clipboardSupportsImages()) throw new Error('Copying images is not available in this browser.');
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': pngOf(image) })]);
  },
  get writeContent() { return clipboardSupportsImages() ? writeContent : undefined; },
};
