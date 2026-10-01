import { toast } from "sonner";
import type { FileActions, FileSource, FileMutationResult, ManagedFileAsset } from "@text-to-cad/ui/file-viewer";
import type { ExternalEntryAction } from "@text-to-cad/ui/file-viewer";
import { closeSessionTab, readSessionStrip, revealSessionPath, useExplorer } from "@renderer/state/explorer";
import { desktopSourceId } from "@renderer/state/live-documents";
import type { FileMutationResult as NativeMutationResult } from "@shared/ipc/explorer";
import type { ExplorerRoot } from "@shared/types";
import { platform } from "@renderer/lib/platform";
import { messageOf, performEntryAction, requestAt } from "../entry-actions";
import type { EntryActionContext } from "../entry-actions";
import { viewerFileChange } from "../file-changes";

/** Every operation is bound to a validated project/root pair before entering UI. */
export function createDesktopFileSource({ sessionId, projectId, projectName, root }: { sessionId: string; projectId: string; projectName: string | (() => string); root: ExplorerRoot }): FileSource {
  const context = { projectId, root };
  const at = requestAt(context);
  const id = desktopSourceId(projectId, root);
  const listeners = new Set<Parameters<NonNullable<FileSource["subscribe"]>>[0]>();
  let unsubscribe: (() => void) | undefined;
  // The files this tab has opened: main keeps what it needs to follow each
  // through a move until the tab gives them back on its unwatch. Given back
  // and subscribed again (a remount), they are held again. A set, not a count
  // per stat: a file rewritten every few hundred ms restats on each reload,
  // and a payload of one path per stat outgrows the channel's cap.
  let opened = new Set<string>();
  let released = new Set<string>();
  const checked = async <T>(signal: AbortSignal, operation: () => Promise<T>): Promise<T> => {
    signal.throwIfAborted();
    const result = await operation();
    signal.throwIfAborted();
    return result;
  };
  const mutate = async (signal: AbortSignal, operation: () => Promise<NativeMutationResult>, effect?: "trash" | "reveal"): Promise<FileMutationResult> => {
    if (signal.aborted) return { status: "cancelled" };
    // IPC cannot undo a dispatched write. Always reconcile a committed receipt,
    // even when the initiating tab was closed while main finished the operation.
    try {
      const result = await operation();
      if (result.status !== "committed") return result;
      useExplorer.getState().receiveChanges(projectId, root, [result.change]);
      // The filesystem receipt is shared, but UI effects belong only to the
      // originating session, including when the user has switched away.
      try {
        if (effect === "trash") {
          const strip = await readSessionStrip(sessionId);
          // Each tab on its own: one with unsaved changes refuses to close, and the rest still do.
          const left: string[] = [];
          for (const tab of strip.tabs) {
            if (tab.kind === "file" && tab.root === root && tab.path !== null && (tab.path === result.path || tab.path.startsWith(`${result.path}/`))) {
              try { await closeSessionTab(sessionId, tab.id); } catch (error) { left.push(`${tab.path} (${messageOf(error)})`); }
            }
          }
          if (left.length > 0) toast.error(`Moved to Trash, but ${left.length === 1 ? "1 open tab" : `${left.length} open tabs`} could not be closed: ${left.join("; ")}`);
        }
        if (effect === "reveal") await revealSessionPath(sessionId, projectId, root, result.path, result.change.directory);
      } catch { /* A closed/archived session cannot revoke a committed file operation. */ }
      return { ...result, change: viewerFileChange(result.change) };
    } catch (error) { return { status: "failed", code: "error", message: messageOf(error) }; }
  };
  return {
    id,
    get rootName() { return typeof projectName === "function" ? projectName() : projectName; },
    async stat(path, { signal }) {
      // The viewer stats a file as it opens it: this is the one stat that counts as an open
      // (file_opened) and watches the entry. Attachments and integrations stat without it.
      // Only the first stat of a path says so: main takes one hold per open-stat and this
      // record gives back one per path, so a reload's restat is a plain stat.
      signal.throwIfAborted();
      const stat = await window.textToCad.explorer.stat({ ...at, path, ...(opened.has(path) ? {} : { intent: "open" as const }) });
      // Counted before the abort check: main counted it when it answered.
      if (stat.kind === "file") opened.add(stat.path);
      signal.throwIfAborted();
      return { ...stat, mediaType: stat.fileKind };
    },
    list: (path, { signal }) => checked(signal, () => window.textToCad.explorer.list({ ...at, path })),
    // `truncated` rides along: the filter says when the index stopped short of the project.
    paths: ({ signal }) => checked(signal, () => window.textToCad.explorer.paths({ ...at, path: "" })),
    readText: (path, { signal }) => checked(signal, () => window.textToCad.explorer.readText({ ...at, path })),
    async readAsset(path, { signal }): Promise<ManagedFileAsset> {
      const binary = await checked(signal, () => window.textToCad.explorer.readBinary({ ...at, path }));
      // IPC returns a base64 data URL. Decode locally: Electron's connect-src
      // permits no data: fetch, even though its image policy permits the asset.
      const encoded = binary.dataUrl.slice(binary.dataUrl.indexOf(",") + 1);
      const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
      const blob = new Blob([bytes], { type: binary.mime });
      signal.throwIfAborted();
      const url = URL.createObjectURL(blob);
      return { url, bytes, mime: binary.mime, release: () => URL.revokeObjectURL(url) };
    },
    async writeText(path, { content, expectedRevision, signal }) {
      if (signal.aborted) return { status: "cancelled" };
      try {
        const result = await window.textToCad.explorer.writeText({ ...at, path, content, expectedRevision });
        if (result.status === "saved") useExplorer.getState().receiveChanges(projectId, root, [{ kind: "changed", path, directory: false, revision: result.document.revision }]);
        return result;
      } catch (error) { return { status: "error", code: "error", message: messageOf(error) }; }
    },
    rename: (path, { name, signal }) => mutate(signal, () => window.textToCad.explorer.rename({ ...at, path, name })),
    create: (directory, { kind, name, signal }) => mutate(signal, () => kind === "file"
      ? window.textToCad.explorer.createFile({ ...at, path: directory, name })
      : window.textToCad.explorer.createDirectory({ ...at, path: directory, name }), kind === "directory" ? "reveal" : undefined),
    duplicate: (path, { signal }) => mutate(signal, () => window.textToCad.explorer.duplicate({ ...at, path }), "reveal"),
    trash: (path, { signal }) => mutate(signal, () => window.textToCad.explorer.trash({ ...at, path }), "trash"),
    subscribe(listener) {
      listeners.add(listener);
      if (!unsubscribe) {
        const again = [...released];
        for (const path of released) opened.add(path);
        released = new Set();
        void window.textToCad.explorer.watch({ ...at, ...(again.length ? { paths: again } : {}) }).catch(() => {});
        unsubscribe = useExplorer.subscribe((next, previous) => {
          if (next.projectId === projectId && next.fsRevision !== previous.fsRevision && next.changedRoot === root) {
            // Main moves its holds with a moved file; so does this record.
            for (const entry of next.changedEntries) {
              if (entry.kind !== "moved" || !opened.delete(entry.previousPath)) continue;
              opened.add(entry.path);
            }
            const change = { sourceId: id, changes: next.changedEntries.map(viewerFileChange) };
            for (const subscriber of listeners) subscriber(change);
          }
        });
      }
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0) {
          unsubscribe?.(); unsubscribe = undefined;
          const paths = [...opened];
          released = opened;
          opened = new Set();
          void window.textToCad.explorer.unwatch({ ...at, ...(paths.length ? { paths } : {}) }).catch(() => {});
        }
      };
    },
  };
}

export function createDesktopFileActions(context: EntryActionContext): FileActions {
  const actions: ExternalEntryAction[] = ["open-default", "open-with", "reveal", "copy-path", "copy-relative-path", "copy-reference", "open-terminal"];
  return { platform, perform: Object.fromEntries(actions.map(action => [action,
    (entry: Parameters<typeof performEntryAction>[1]) => performEntryAction(action, entry, context)])) };
}
