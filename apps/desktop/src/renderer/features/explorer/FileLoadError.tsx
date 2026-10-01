import { FileText, FileWarning } from "lucide-react";
import { useEffect, useState } from "react";

import type { FileSource } from "@text-to-cad/ui/file-viewer";
import { EmptyState } from "@text-to-cad/ui/navigation";

import { formatBytes } from "./renderers/image/ImageRenderer";
import { OpenExternally } from "./renderers/unsupported/OpenExternally";

/**
 * The most a binary preview (an image, a PDF) reads. It mirrors `MAX_BINARY_BYTES` in
 * `src/main/explorer/fs.ts`, which the renderer cannot import; `tests/unit/renderer/file-preview-errors.test.tsx`
 * fails when the two drift.
 */
export const PREVIEW_LIMIT_BYTES = 24 * 1024 * 1024;

/** The sentence `readAsset` is refused with when the file is over the limit. */
export const TOO_LARGE = "too large to preview";

/**
 * What the viewer shows when a file did not open. One that is only too big for the
 * preview says how big, what the limit is, and offers the system's own app; any other
 * failure keeps the plain card with the message it was given.
 */
export function FileLoadError({ message, path, source }: { message: string; path: string | null; source: FileSource }) {
  const tooLarge = message.includes(TOO_LARGE);
  const [size, setSize] = useState<number | null>(null);
  useEffect(() => {
    if (!tooLarge || !path) return undefined;
    const controller = new AbortController();
    source.stat(path, { signal: controller.signal }).then(stat => setSize(stat.size ?? null), () => {});
    return () => controller.abort();
  }, [tooLarge, path, source]);
  if (!tooLarge || !path) return <EmptyState icon={FileText} title="Could not open that file" description={message} tone="warn" />;
  const name = path.split("/").pop() || path;
  return (
    <EmptyState
      action={<OpenExternally path={path} />}
      description={`${name} is ${size === null ? "larger than the preview limit" : formatBytes(size)}; previews open files up to ${formatBytes(PREVIEW_LIMIT_BYTES)}.`}
      icon={FileWarning}
      title="This file is too large to preview"
      tone="warn"
    />
  );
}
