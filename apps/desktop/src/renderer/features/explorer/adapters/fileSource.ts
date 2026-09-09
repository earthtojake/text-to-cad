import type { FileSource, ManagedFileAsset } from "@hardcore/ui/file-viewer";
import type { ExternalEntryAction } from "@hardcore/ui/file-viewer";
import { useExplorer } from "@renderer/state/explorer";
import type { ExplorerRoot } from "@shared/types";
import { createEntry, currentPlatform, messageOf, performEntryAction, renameEntry, requestAt, trashEntry } from "../entry-actions";

/** Every operation is bound to a validated project/root pair before entering UI. */
export function createDesktopFileSource({ projectId, projectName, root }: { projectId: string; projectName: string | (() => string); root: ExplorerRoot }): FileSource {
  const context = { projectId, root, platform: currentPlatform(), beginRename: () => {}, beginCreate: () => {} };
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
  const actions: ExternalEntryAction[] = ["open-default", "open-with", "reveal", "copy-path", "copy-relative-path", "copy-reference", "open-terminal", "duplicate"];
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
      return { url, mime: binary.mime, release: () => URL.revokeObjectURL(url) };
    },
    async writeText(path, { content, expectedRevision, signal }) {
      try {
        const document = await checked(signal, () => window.hardcore.explorer.writeText({ ...at, path, content, expectedRevision }));
        return { status: "saved", document };
      } catch (error) {
        signal.throwIfAborted();
        const message = messageOf(error);
        // This is the explicit optimistic-lock failure from main's fs contract.
        return message === "the file changed on disk since it was opened"
          ? { status: "conflict", message }
          : { status: "error", message };
      }
    },
    subscribe(listener) {
      listeners.add(listener);
      if (!unsubscribe) {
        void window.hardcore.explorer.watch(at).catch(() => {});
        unsubscribe = useExplorer.subscribe((next, previous) => {
          if (next.projectId === projectId && next.fsRevision !== previous.fsRevision && next.changedRoot === root) {
            const change = { sourceId: id, paths: next.changedPaths };
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
    actions: {
      platform: context.platform,
      perform: Object.fromEntries(actions.map((action) => [action, (entry: Parameters<typeof performEntryAction>[1]) => performEntryAction(action, entry, context)])),
      rename: (entry, name) => renameEntry(entry, name, context),
      create: (directory, kind, name) => createEntry(directory, kind, name, context),
      trash: (entry) => trashEntry(entry, context),
    },
  };
}
