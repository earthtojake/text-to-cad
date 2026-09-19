/** Native/menu effects belong to the host, separate from FileSource mutations. */
import { createPromptContext, referencePart } from "@hardcore/core/prompt";
import type { PromptContextPort } from "@hardcore/core/prompt";
import type { ExternalEntryAction, FileEntry } from "@hardcore/ui/file-viewer";
import type { ClipboardPort } from "@hardcore/ui/host";
import type { Platform } from "@hardcore/ui/navigation";
import { openSessionTab } from "@renderer/state/explorer";
import type { ExplorerRoot } from "@shared/types";

export type EntryActionContext = {
  sessionId: string;
  projectId: string;
  root: ExplorerRoot;
  sourceId: string;
  clipboard: ClipboardPort;
  promptContext: PromptContextPort;
};

export function requestAt(ctx: Pick<EntryActionContext, "projectId" | "root">) {
  return { projectId: ctx.projectId, ...(ctx.root ? { root: ctx.root } : {}) };
}

export function currentPlatform(): Platform {
  const agent = navigator.userAgent;
  return agent.includes("Macintosh") ? "darwin" : agent.includes("Windows") ? "win32" : "linux";
}

export async function performEntryAction(action: ExternalEntryAction, entry: Pick<FileEntry, "path" | "kind">, ctx: EntryActionContext): Promise<void> {
  const at = { ...requestAt(ctx), path: entry.path };
  switch (action) {
    case "open-default": await window.hardcore.explorer.openDefault(at); return;
    case "open-with": await window.hardcore.explorer.openWith(at); return;
    case "reveal": await window.hardcore.explorer.reveal(at); return;
    case "copy-path": {
      const { path } = await window.hardcore.explorer.absolutePath(at);
      await ctx.clipboard.writeText(path); return;
    }
    case "copy-relative-path": await ctx.clipboard.writeText(entry.path); return;
    case "copy-reference": {
      const context = createPromptContext([referencePart({
        resource: { kind: "workspace-file", workspaceId: ctx.sourceId, path: entry.path }, target: { kind: "whole-resource" },
      })]);
      // Preserve this explicit Copy command's clipboard effect. Start both
      // effects during the gesture so delivery binds its draft before a wait.
      const [, result] = await Promise.all([
        ctx.clipboard.writeText(entry.path), ctx.promptContext.deliver(context),
      ]);
      if (result.status === "failed" || result.status === "deferred" || result.status === "partial") throw new Error(result.message || "Reference could not be delivered.");
      return;
    }
    case "open-terminal": {
      const { path } = await window.hardcore.explorer.absolutePath(at);
      await openSessionTab(ctx.sessionId, ctx.projectId, ctx.root, "terminal", { cwd: path });
      return;
    }
  }
}

/** Electron wraps a thrown IpcError as "Error invoking remote method '…': Error: …". */
export function messageOf(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  const at = message.lastIndexOf("Error: ");
  return at >= 0 ? message.slice(at + 7) : message;
}
