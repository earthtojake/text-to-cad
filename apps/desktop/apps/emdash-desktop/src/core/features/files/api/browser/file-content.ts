import { encodeResourceUri, type HostFileRef } from '@emdash/core/primitives/path/api';
import { createScope } from '@emdash/shared/concurrency';
import { observe, pin, remote } from '@emdash/wire/state';
import { filesWireContract, type FilesContentModel } from '../contract';
import { getFilesClient } from './client';

/**
 * Watches a file's disk content and invokes `onChange` with every snapshot.
 * Intended for config-file watchers (e.g. `.emdash.json`), not open editors —
 * editor tabs acquire interest through OpenFileStore instead.
 */
export async function watchFileContent(
  ref: HostFileRef,
  onChange: (content: FilesContentModel) => void
): Promise<() => void> {
  if (typeof window === 'undefined') return () => {};
  const client = await getFilesClient();
  const uri = encodeResourceUri(ref);
  const scope = createScope({ label: `watch-file-content:${uri}` });
  const contentRemote = remote(filesWireContract.content, client.content, { scope, lingerMs: 0 });
  const model = contentRemote({ uri, source: 'disk' });
  pin(scope, [model.states.content]);
  observe(
    model.states.content,
    (current) => {
      if (current.value) onChange(current.value);
    },
    { scope }
  );
  let disposed = false;
  return () => {
    if (disposed) return;
    disposed = true;
    void (async () => {
      try {
        await contentRemote.dispose();
      } finally {
        await scope.dispose();
      }
    })();
  };
}

/** Reads an image file's bytes and returns them as a data URL for previews. */
/**
 * Previews read whole files. The runtime's default cap (200 KB) is sized for
 * text; a render or a drawing PDF is routinely a few megabytes.
 */
export const PREVIEW_MAX_BYTES = 64 * 1024 * 1024;

export async function readImageFile(ref: HostFileRef) {
  const client = await getFilesClient();
  const result = await client.fs.readBytes({
    uri: encodeResourceUri(ref),
    options: { maxBytes: PREVIEW_MAX_BYTES },
  });
  if (!result.success) return result;
  const bytes = await result.data.bytes();
  const buffer = new ArrayBuffer(bytes.byteLength);
  new Uint8Array(buffer).set(bytes);
  const dataUrl = await blobToDataUrl(new Blob([buffer], { type: result.data.meta.mimeType }));
  return {
    success: true as const,
    data: {
      dataUrl,
      mimeType: result.data.meta.mimeType,
      size: result.data.meta.totalSize,
      truncated: result.data.meta.truncated,
    },
  };
}

function blobToDataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener('load', () => resolve(String(reader.result)), { once: true });
    reader.addEventListener('error', () => reject(reader.error ?? new Error('Image read failed')), {
      once: true,
    });
    reader.readAsDataURL(blob);
  });
}
