import type { FileChange as ViewerFileChange } from "@hardcore/ui/file-viewer";
import type { FileChange } from "@shared/ipc/explorer";

/** The validated native event uses filesystem names; shared UI uses storage semantics. */
export function viewerFileChange(change: FileChange): ViewerFileChange {
  const entryKind = change.directory ? "directory" : "file";
  if (change.kind === "moved") return { kind: "moved", from: change.previousPath, to: change.path, entryKind };
  if (change.kind === "added") return { kind: "added", path: change.path, entryKind };
  if (change.kind === "removed") return { kind: "deleted", path: change.path, entryKind };
  return { kind: change.directory ? "metadata" : "content", path: change.path, revision: change.revision };
}
