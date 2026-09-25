import { ExternalLink, FileQuestion } from "lucide-react";

import type { FileRendererProps } from "@hardcore/ui/file-viewer";
import { EmptyState } from "@hardcore/ui/navigation";
import { Button } from "@hardcore/ui/primitives/button";
import { useViewerHost } from "@hardcore/ui/host";

import { formatBytes } from "../image/ImageRenderer";

/** A visible fallback for files without a renderer; no file contents are read. */
export type UnsupportedRendererData = null;

export default function UnsupportedRenderer({
  file,
}: FileRendererProps<UnsupportedRendererData>) {
  const openDefault = useViewerHost().fileActions?.perform?.["open-default"];
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
