import { GitCompare } from "lucide-react";

import { runUiCommand } from "@renderer/state/bridge";

/**
 * Codex's floating pill above the composer: `22 files changed +671 −26`.
 * The counts are the session row's (main tallies the diffs the agent
 * reports, plan §5); clicking sends `open-review`, which the explorer's
 * Review tab answers (P3).
 */
export function FilesChangedPill({
  files,
  insertions,
  deletions,
}: {
  files: number;
  insertions: number;
  deletions: number;
}) {
  if (files === 0) {
    return null;
  }
  return (
    <div className="pointer-events-none flex justify-center">
      <button
        className="pointer-events-auto inline-flex h-7 items-center gap-2 rounded-full border bg-background px-3 text-[12px] shadow-xs transition-colors hover:bg-accent"
        data-files-changed
        onClick={() => runUiCommand("open-review")}
        type="button"
      >
        <GitCompare className="size-3.5 text-muted-foreground" />
        <span>
          {files} {files === 1 ? "file" : "files"} changed
        </span>
        <span className="font-mono text-[11px] text-muted-foreground tabular-nums">
          +{insertions} −{deletions}
        </span>
      </button>
    </div>
  );
}
