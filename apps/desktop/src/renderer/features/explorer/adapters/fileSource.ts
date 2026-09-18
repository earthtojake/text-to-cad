import type { FileActions, FileSource, FileMutationResult, ManagedFileAsset } from "@hardcore/ui/file-viewer";
import type { ExternalEntryAction } from "@hardcore/ui/file-viewer";
import { closeSessionTab, readSessionStrip, revealSessionPath, useExplorer } from "@renderer/state/explorer";
import type { FileMutationResult as NativeMutationResult } from "@shared/ipc/explorer";
import type { ExplorerRoot } from "@shared/types";
import { currentPlatform, messageOf, performEntryAction, requestAt } from "../entry-actions";
import type { EntryActionContext } from "../entry-actions";
import { viewerFileChange } from "../file-changes";

/** Every operation is bound to a validated project/root pair before entering UI. */
export function createDesktopFileSource({ sessionId, projectId, projectName, root }: { sessionId: string; projectId: string; projectName: string | (() => string); root: ExplorerRoot }): FileSource {
  const context = { projectId, root };
  const at = requestAt(context);
  const id = JSON.stringify(["desktop", projectId, root]);
  const listeners = new Set<Parameters<NonNullable<FileSource["subscribe"]>>[0]>();
  let unsubscribe: (() => void) | undefined;
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
          for (const tab of strip.tabs) {
            if (tab.kind === "file" && tab.root === root && tab.path !== null && (tab.path === result.path || tab.path.startsWith(`${result.path}/`))) await closeSessionTab(sessionId, tab.id);
          }
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
      const stat = await checked(signal, () => window.hardcore.explorer.stat({ ...at, path }));
      return { ...stat, mediaType: stat.fileKind };
    },
    list: (path, { signal }) => checked(signal, () => window.hardcore.explorer.list({ ...at, path })),
    paths: ({ signal }) => checked(signal, async () => (await window.hardcore.explorer.paths({ ...at, path: "" })).paths),
    readText: (path, { signal }) => checked(signal, () => window.hardcore.explorer.readText({ ...at, path })),
    async readAsset(path, { signal }): Promise<ManagedFileAsset> {
      const binary = await checked(signal, () => window.hardcore.explorer.readBinary({ ...at, path }));
      // IPC returns a base64 data URL. Decode locally: Electron's connect-src
      // permits no data: fetch, even though its image policy permits the asset.
      const encoded = binary.dataUrl.slice(binary.dataUrl.indexOf(",") + 1);
      const bytes = Uint8Array.from(atob(encoded), character => character.charCodeAt(0));
      const blob = new Blob([bytes], { type: binary.mime });
      signal.throwIfAborted();
      const url = URL.createObjectURL(blob);
      return { url, bytes, mime: binary.mime, byteLength: binary.size, resource: { kind: "workspace-file", workspaceId: id, path: binary.path }, release: () => URL.revokeObjectURL(url) };
    },
    async writeText(path, { content, expectedRevision, signal }) {
      if (signal.aborted) return { status: "cancelled" };
      try {
        const result = await window.hardcore.explorer.writeText({ ...at, path, content, expectedRevision });
        if (result.status === "saved") useExplorer.getState().receiveChanges(projectId, root, [{ kind: "changed", path, directory: false, revision: result.document.revision }]);
        return result;
      } catch (error) { return { status: "error", code: "error", message: messageOf(error) }; }
    },
    rename: (path, { name, signal }) => mutate(signal, () => window.hardcore.explorer.rename({ ...at, path, name })),
    create: (directory, { kind, name, signal }) => mutate(signal, () => kind === "file"
      ? window.hardcore.explorer.createFile({ ...at, path: directory, name })
      : window.hardcore.explorer.createDirectory({ ...at, path: directory, name }), kind === "directory" ? "reveal" : undefined),
    duplicate: (path, { signal }) => mutate(signal, () => window.hardcore.explorer.duplicate({ ...at, path }), "reveal"),
    trash: (path, { signal }) => mutate(signal, () => window.hardcore.explorer.trash({ ...at, path }), "trash"),
    subscribe(listener) {
      listeners.add(listener);
      if (!unsubscribe) {
        void window.hardcore.explorer.watch(at).catch(() => {});
        unsubscribe = useExplorer.subscribe((next, previous) => {
          if (next.projectId === projectId && next.fsRevision !== previous.fsRevision && next.changedRoot === root) {
            const change = { sourceId: id, changes: next.changedEntries.map(viewerFileChange) };
            for (const subscriber of listeners) subscriber(change);
          }
        });
      }
      return () => {
        listeners.delete(listener);
        if (listeners.size === 0) {
          unsubscribe?.(); unsubscribe = undefined;
          void window.hardcore.explorer.unwatch(at).catch(() => {});
        }
      };
    },
  };
}

export function createDesktopFileActions(context: EntryActionContext): FileActions {
  const actions: ExternalEntryAction[] = ["open-default", "open-with", "reveal", "copy-path", "copy-relative-path", "copy-reference", "open-terminal"];
  return { platform: currentPlatform(), perform: Object.fromEntries(actions.map(action => [action,
    (entry: Parameters<typeof performEntryAction>[1]) => performEntryAction(action, entry, context)])) };
}
