import { FileQuestion } from "lucide-react";

import type { FileRendererProps } from "@text-to-cad/ui/file-viewer";
import { EmptyState } from "@text-to-cad/ui/navigation";

import { formatBytes } from "../image/ImageRenderer";
import { OpenExternally } from "./OpenExternally";

/** A visible fallback for files without a renderer; no file contents are read. */
export type UnsupportedRendererData = null;

export default function UnsupportedRenderer({
  file,
}: FileRendererProps<UnsupportedRendererData>) {
  return (
    <EmptyState
      action={<OpenExternally path={file.path} />}
      description={`${file.name} is ${formatBytes(file.size)}${
        file.extension ? ` of ${file.extension.toUpperCase()}` : ""
      }. This file type does not have a preview.`}
      icon={FileQuestion}
      title="Not supported"
    />
  );
}
