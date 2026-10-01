import { ExternalLink } from "lucide-react";

import { Button } from "@text-to-cad/ui/primitives/button";
import { useViewerHost } from "@text-to-cad/ui/host";

/** The way out of a preview that cannot be shown: the system's own app for the file. Nothing when the host has none. */
export function OpenExternally({ path }: { path: string }) {
  const openDefault = useViewerHost().fileActions?.perform?.["open-default"];
  if (!openDefault) return null;
  return (
    <Button className="h-7 gap-1.5 text-xs font-medium" onClick={() => void openDefault({ path, kind: "file" })} size="sm" variant="secondary">
      <ExternalLink className="size-3.5" />
      Open externally
    </Button>
  );
}
