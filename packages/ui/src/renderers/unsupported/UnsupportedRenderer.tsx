import { ExternalLink, FileQuestion } from "lucide-react";

import type { FileRendererProps } from "../../file-viewer/types.js";
import { EmptyState } from "../../file-viewer/navigation/index.js";
import { Button } from "../../primitives/button.jsx";

import { formatBytes } from "../image/ImageRenderer.js";

/**
 * The fallback: a file this app has no reading of.
 *
 * It says what it is and hands the file to the operating system, which does
 * have a reading of it. What it deliberately does not do is show a hex dump or
 * the bytes decoded as latin-1 — neither is something a person wants, and both
 * look like the app failing rather than declining.
 */
export type UnsupportedRendererData = null;

export default function UnsupportedRenderer({
  file,
  source,
}: FileRendererProps<UnsupportedRendererData>) {
  const openDefault = source.actions?.perform?.["open-default"];
  return (
    <EmptyState
      action={
        openDefault ? (
          <Button
            className="h-7 gap-1.5 text-xs font-medium"
            onClick={() => void openDefault({ path: file.path, kind: "file" })}
            size="sm"
            variant="secondary"
          >
            <ExternalLink className="size-3.5" />
            Open externally
          </Button>
        ) : undefined
      }
      description={`${file.name} is ${formatBytes(file.size)}${
        file.extension ? ` of ${file.extension.toUpperCase()}` : ""
      }. Hardcore has no preview for it, but your system probably does.`}
      icon={FileQuestion}
      title="No preview for this file"
    />
  );
}
