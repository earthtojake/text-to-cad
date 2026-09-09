import { FileInput } from "lucide-react";
import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@renderer/components/ui/button";
import { useExplorer } from "@renderer/state/explorer";
import type { ExplorerRoot } from "@shared/types";

/** The desktop's native Add files action, shared by the explorer and empty viewer. */
export function AddFilesButton({ projectId, root }: { projectId: string; root: ExplorerRoot }) {
  const [adding, setAdding] = useState(false);
  const addFiles = async () => {
    if (adding) return;
    const { activeId, root: workspaceRoot } = useExplorer.getState();
    setAdding(true);
    try {
      const result = await window.hardcore.explorer.addFiles({ projectId, ...(root ? { root } : {}) });
      if (!result) return;
      const current = useExplorer.getState();
      if (result.paths.length && current.projectId === projectId && current.root === workspaceRoot && current.activeId === activeId) {
        current.openFile(result.paths[0]!, root);
      }
      if (result.paths.length) toast.success(result.paths.length === 1 ? `Added ${result.paths[0]}` : `Added ${result.paths.length} files`);
      if (result.errors.length) toast.error(result.errors.join("\n"));
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not add files.");
    } finally {
      setAdding(false);
    }
  };

  return <Button className="h-7 gap-1.5 text-xs" disabled={adding} onClick={() => void addFiles()}
    size="sm" type="button" variant="outline" title="Copy files into this project — STEP, images, PDFs, code and more">
    <FileInput aria-hidden className="size-3.5" />{adding ? "Adding files…" : "Add files…"}
  </Button>;
}
