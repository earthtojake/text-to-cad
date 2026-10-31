import type { ClipboardPort } from '@text-to-cad/ui/host';

/**
 * Text copied by the page's own selection and copy command, for a frame whose host did not grant
 * it the clipboard (the resource asks for `clipboardWrite`, and a host may refuse it or have no
 * clipboard API in its sandbox): the command still copies what a press asked for, inside the
 * moment the press gave the page. False where it could not. The page's selection and focus are
 * put back as they were.
 */
function copyBySelection(text: string): boolean {
  if (!document.body || typeof document.execCommand !== 'function') return false;
  const focused = document.activeElement;
  const selection = document.getSelection();
  const ranges = selection ? Array.from({ length: selection.rangeCount }, (_, index) => selection.getRangeAt(index)) : [];
  const field = document.createElement('textarea');
  field.value = text;
  field.readOnly = true;
  field.setAttribute('aria-hidden', 'true');
  field.style.cssText = 'position:fixed;top:0;left:-9999px;width:1px;height:1px;opacity:0';
  document.body.append(field);
  try {
    field.focus({ preventScroll: true });
    field.select();
    return document.execCommand('copy');
  } catch {
    return false;
  } finally {
    field.remove();
    if (selection) {
      selection.removeAllRanges();
      for (const range of ranges) selection.addRange(range);
    }
    if (focused instanceof HTMLElement && focused !== document.body) focused.focus({ preventScroll: true });
  }
}

/**
 * The page's own clipboard. The host grants its frame clipboard writes (the resource asks for
 * `clipboardWrite`); a host that does not, or whose sandbox has no clipboard API, still lets the
 * page's copy command copy text. Reading is the host's to allow and may be refused.
 */
export const frameClipboard: ClipboardPort = {
  async writeText(text) {
    let refused: unknown = null;
    if (typeof text === 'string') {
      if (navigator.clipboard?.writeText) {
        try { await navigator.clipboard.writeText(text); return; } catch (error) { refused = error; }
      }
      if (copyBySelection(text)) return;
      throw refused ?? new Error('Copying is not available here.');
    }
    // Still on its way: the write starts now, in the gesture, and takes the text when it arrives.
    if (navigator.clipboard?.write && typeof ClipboardItem === 'function') {
      const blob = text.then(value => new Blob([value], { type: 'text/plain' }));
      try { await navigator.clipboard.write([new ClipboardItem({ 'text/plain': blob })]); return; }
      catch (error) { await blob; refused = error; }
    }
    // A clipboard that takes no pending text gets the text itself, once it has arrived.
    if (copyBySelection(await text)) return;
    throw refused ?? new Error('Copying is not available here.');
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
