/**
 * What each item of the entry menu does (`entry-menu.ts` says what there is).
 *
 * The tree's rows and the breadcrumb's crumbs share these, so the two menus
 * do not just look alike, they are the same code. Everything that touches
 * the disk goes through main (`explorer.*`), which resolves every path
 * against the root and refuses one outside it; what is left here is the
 * clipboard, the composer, and keeping the strip and the tree honest about
 * an entry that just changed its name or stopped existing.
 *
 * Two items are UI rather than IPC — `Rename` and the two `New …` — and are
 * handed back to the caller through the context, because an inline field is
 * the tree's or the crumb's to draw.
 */
import { toast } from "sonner";

import { NEW_SESSION_KEY, useComposer } from "@renderer/state/composer";
import { useExplorer } from "@renderer/state/explorer";
import { useSessions } from "@renderer/state/sessions";
import type { DirEntry } from "@shared/ipc/explorer";
import type { ExplorerRoot, ExplorerTab } from "@shared/types";

import { parentOf } from "./crumbs";
import type { EntryAction, MenuEntryTarget, Platform } from "./entry-menu";

export type EntryActionContext = {
  projectId: string;
  root: ExplorerRoot;
  platform: Platform;
  /** Draw an inline field over the entry's name; `renameEntry` finishes it. */
  beginRename: (entry: MenuEntryTarget) => void;
  /** Draw an inline field for a new entry in `directory`; `createEntry` finishes it. */
  beginCreate: (directory: string, kind: "file" | "directory") => void;
};

/** The `{ projectId, root? }` every explorer request starts with. */
export function requestAt(ctx: Pick<EntryActionContext, "projectId" | "root">) {
  return { projectId: ctx.projectId, ...(ctx.root ? { root: ctx.root } : {}) };
}

/** Which OS the renderer is on, for the menu's labels and shortcuts. */
export function currentPlatform(): Platform {
  const agent = navigator.userAgent;
  return agent.includes("Macintosh") ? "darwin" : agent.includes("Windows") ? "win32" : "linux";
}

export async function performEntryAction(
  action: EntryAction,
  entry: MenuEntryTarget,
  ctx: EntryActionContext,
): Promise<void> {
  const at = requestAt(ctx);
  const explorer = useExplorer.getState();
  try {
    switch (action) {
      case "open":
        explorer.openFile(entry.path, ctx.root);
        return;
      case "open-default":
        await window.hardcore.explorer.openDefault({ ...at, path: entry.path });
        return;
      case "open-with":
        await window.hardcore.explorer.openWith({ ...at, path: entry.path });
        return;
      case "reveal":
        await window.hardcore.explorer.reveal({ ...at, path: entry.path });
        return;
      case "copy-path": {
        const { path } = await window.hardcore.explorer.absolutePath({ ...at, path: entry.path });
        await navigator.clipboard.writeText(path);
        return;
      }
      case "copy-relative-path":
        await navigator.clipboard.writeText(entry.path);
        return;
      case "copy-reference":
        // The token the composer understands, and a chip in the box beside
        // the clipboard — the same two places the viewer's own Copy
        // Reference lands (`renderers/CadRenderer.tsx`).
        await navigator.clipboard.writeText(entry.path);
        useComposer.getState().insertReference(useSessions.getState().activeId ?? NEW_SESSION_KEY, {
          file: entry.path,
          selector: "",
        });
        return;
      case "new-file":
        ctx.beginCreate(entry.path, "file");
        return;
      case "new-folder":
        ctx.beginCreate(entry.path, "directory");
        return;
      case "open-terminal": {
        const { path } = await window.hardcore.explorer.absolutePath({ ...at, path: entry.path });
        explorer.open("terminal", { cwd: path });
        return;
      }
      case "rename":
        ctx.beginRename(entry);
        return;
      case "duplicate": {
        const { path } = await window.hardcore.explorer.duplicate({ ...at, path: entry.path });
        await reloadDirectory(ctx, parentOf(entry.path));
        useExplorer.getState().setReveal({ path, directory: entry.kind === "directory", root: ctx.root });
        return;
      }
      case "trash":
        await trashEntry(entry, ctx);
        return;
    }
  } catch (error) {
    toast.error(messageOf(error));
  }
}

/**
 * Finish a rename: the disk, then every tab and every open folder that
 * named the old path. Answers the new path, or null when it failed (the
 * field stays up so the person can fix the name).
 */
export async function renameEntry(
  entry: MenuEntryTarget,
  name: string,
  ctx: Pick<EntryActionContext, "projectId" | "root">,
): Promise<string | null> {
  if (name === entry.path.split("/").pop()) {
    return entry.path;
  }
  try {
    const { path } = await window.hardcore.explorer.rename({ ...requestAt(ctx), path: entry.path, name });
    const explorer = useExplorer.getState();
    // The strip: a tab showing the file, or a file under the folder.
    for (const tab of explorer.tabs) {
      const moved = movedPath(tab, ctx.root, entry.path, path);
      if (moved !== null) {
        explorer.update(tab.id, { path: moved });
      }
    }
    // The tree: a folder that was open stays open under its new name.
    explorer.setTreeOpen(ctx.root, (current) => {
      const next = new Set<string>();
      let changed = false;
      for (const directory of current) {
        const moved = movedDirectory(directory, entry.path, path);
        changed ||= moved !== directory;
        next.add(moved);
      }
      return changed ? next : current;
    });
    await reloadDirectory(ctx, parentOf(entry.path));
    return path;
  } catch (error) {
    toast.error(messageOf(error));
    return null;
  }
}

/**
 * Finish a `New file` / `New folder`. A new file opens, the way every
 * editor's does — it is the next thing the person will type into.
 */
export async function createEntry(
  directory: string,
  kind: "file" | "directory",
  name: string,
  ctx: Pick<EntryActionContext, "projectId" | "root">,
): Promise<string | null> {
  try {
    const request = { ...requestAt(ctx), path: directory, name };
    const { path } =
      kind === "file"
        ? await window.hardcore.explorer.createFile(request)
        : await window.hardcore.explorer.createDirectory(request);
    await reloadDirectory(ctx, directory);
    const explorer = useExplorer.getState();
    if (kind === "file") {
      explorer.openFile(path, ctx.root);
    } else {
      explorer.setReveal({ path, directory: true, root: ctx.root });
    }
    return path;
  } catch (error) {
    toast.error(messageOf(error));
    return null;
  }
}

/** The OS trash. No dialog: the trash is the undo. */
export async function trashEntry(
  entry: MenuEntryTarget,
  ctx: Pick<EntryActionContext, "projectId" | "root">,
): Promise<boolean> {
  try {
    await window.hardcore.explorer.trash({ ...requestAt(ctx), path: entry.path });
    const explorer = useExplorer.getState();
    for (const tab of explorer.tabs) {
      if (tab.kind === "file" && tab.root === ctx.root && tab.path !== null && isSameOrUnder(tab.path, entry.path)) {
        explorer.close(tab.id);
      }
    }
    await reloadDirectory(ctx, parentOf(entry.path));
    return true;
  } catch (error) {
    toast.error(messageOf(error));
    return false;
  }
}

/** Re-read one directory into the store now, rather than when the watcher gets to it. */
export async function reloadDirectory(
  ctx: Pick<EntryActionContext, "projectId" | "root">,
  directory: string,
): Promise<void> {
  const entries: DirEntry[] = await window.hardcore.explorer
    .list({ ...requestAt(ctx), path: directory })
    .catch(() => [] as DirEntry[]);
  useExplorer.getState().setTreeListing(ctx.root, directory, entries);
}

function isSameOrUnder(path: string, ancestor: string): boolean {
  return path === ancestor || path.startsWith(`${ancestor}/`);
}

function movedDirectory(directory: string, from: string, to: string): string {
  if (directory === from) {
    return to;
  }
  return directory.startsWith(`${from}/`) ? `${to}${directory.slice(from.length)}` : directory;
}

/** The tab's path after a rename, or null when the rename did not touch it. */
function movedPath(tab: ExplorerTab, root: ExplorerRoot, from: string, to: string): string | null {
  if (tab.kind !== "file" || tab.root !== root || tab.path === null || !isSameOrUnder(tab.path, from)) {
    return null;
  }
  return movedDirectory(tab.path, from, to);
}

/** Electron wraps a thrown IpcError as "Error invoking remote method '…': Error: …". */
export function messageOf(error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  const at = message.lastIndexOf("Error: ");
  return at >= 0 ? message.slice(at + 7) : message;
}
