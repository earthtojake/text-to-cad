import { ExternalLink, FileQuestion } from "lucide-react";

import { Button } from "@renderer/components/ui/button";

import { EmptyState } from "../EmptyState";
import { formatBytes } from "./ImageRenderer";

/**
 * The fallback: a file this app has no reading of.
 *
 * It says what it is and hands the file to the operating system, which does
 * have a reading of it. What it deliberately does not do is show a hex dump or
 * the bytes decoded as latin-1 — neither is something a person wants, and both
 * look like the app failing rather than declining.
 */
export function BinaryRenderer({
  name,
  size,
  extension,
  onOpenExternally,
}: {
  name: string;
  size: number;
  extension: string;
  onOpenExternally: () => void;
}) {
  return (
    <EmptyState
      action={
        <Button className="h-7 gap-1.5 text-xs" onClick={onOpenExternally} size="sm" variant="secondary">
          <ExternalLink className="size-3.5" />
          Open externally
        </Button>
      }
      description={`${name} is ${formatBytes(size)}${
        extension ? ` of ${extension.toUpperCase()}` : ""
      }. Hardcore has no preview for it, but your system probably does.`}
      icon={FileQuestion}
      title="No preview for this file"
    />
  );
}
