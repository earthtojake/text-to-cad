import { ExternalLink, FileQuestion } from "lucide-react";

import type { FileRendererProps } from "../../file-viewer/types.js";
import { EmptyState } from "../../file-viewer/navigation/index.js";
import { Button } from "../../primitives/button.jsx";

import { formatBytes } from "../image/ImageRenderer.js";

/** A visible fallback for files without a renderer; no file contents are read. */
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
      }. This file type does not have a preview.`}
      icon={FileQuestion}
      title="Not supported"
    />
  );
}
