import type { FileUIPart } from "@renderer/components/ai-elements/types";

/**
 * The files behind the composer's attachments, kept until they are sent.
 *
 * AI Elements' `PromptInput` holds an attachment as a `blob:` URL and, on
 * submit, turns it back into bytes with `fetch(url)`. The renderer is loaded
 * from `file://`, whose origin is opaque, and Chromium refuses to fetch a
 * blob URL from an opaque origin: the fetch throws, the part keeps its blob
 * URL, and `toPromptBlocks` cannot read it — the image is dropped without a
 * word. So every file this app adds — a capture from the viewer, a pasted
 * image, a file from the attach button — is remembered here by name, and
 * `dataUrlOf` reads it with a `FileReader`, which needs no fetch. A drop onto
 * the box goes through the vendored component's own input and is the one
 * path this does not cover.
 */
const remembered = new Map<string, File[]>();

export function rememberFiles(files: readonly File[]): File[] {
  for (const file of files) {
    const list = remembered.get(file.name) ?? [];
    list.push(file);
    remembered.set(file.name, list);
  }
  return [...files];
}

/** The file for an attachment, taken out of the registry; null when unknown. */
function takeFile(part: FileUIPart): File | null {
  const list = remembered.get(part.filename ?? "");
  const file = list?.shift() ?? null;
  if (list && list.length === 0) {
    remembered.delete(part.filename ?? "");
  }
  return file;
}

function readAsDataUrl(file: File): Promise<string | null> {
  return new Promise((resolve) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(typeof reader.result === "string" ? reader.result : null);
    reader.onerror = () => resolve(null);
    reader.readAsDataURL(file);
  });
}

/** An attachment's bytes as a data URL: what it already carries, else the remembered file's. */
export async function dataUrlOf(part: FileUIPart): Promise<string | null> {
  if (part.url?.startsWith("data:")) {
    return part.url;
  }
  const file = takeFile(part);
  return file ? readAsDataUrl(file) : null;
}

/** For the tests. */
export function forgetRememberedFiles(): void {
  remembered.clear();
}
