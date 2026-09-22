import { Ellipsis } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuTrigger } from "../../primitives/dropdown-menu.jsx";
import { EntryContextMenu, EntryMenuItems, FILE_PANEL_TREE, InlineName, parentOf, useEntryMenuFocusGuard } from "../navigation/index.js";
import type { CrumbSource, EntryAction, FileTreeSource, MenuEntryTarget, TreeEdit, TreeEditRequest } from "../navigation/index.js";
import type { FileActions, FileChange, FileEntry, FileMutationResult, FileSource, FileViewerProps, FileViewerState } from "../types.js";
import { movedFilePath, reconcileFileTree } from "../fileChanges.js";
import { errorMessage } from "./useFileDocument.js";
import type { ViewerHost } from "../../host/types.js";

type MenuAction = (action: EntryAction, entry: MenuEntryTarget) => void;
function CrumbActions({ entry, capabilities, platform, onAction }: {
  entry: MenuEntryTarget; capabilities: ReadonlySet<EntryAction>; platform: "darwin" | "win32" | "linux"; onAction: MenuAction;
}) {
  const guard = useEntryMenuFocusGuard(onAction);
  return <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild><button aria-label="File actions" title="File actions" data-testid="crumb-actions" type="button"
      className="flex size-5 shrink-0 items-center justify-center rounded-sm text-muted-foreground outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring data-[state=open]:bg-accent data-[state=open]:text-accent-foreground">
      <Ellipsis className="size-3.5" />
    </button></DropdownMenuTrigger>
    <DropdownMenuContent align="start" className="w-56" data-entry-menu={entry.path} onCloseAutoFocus={guard.onCloseAutoFocus} sideOffset={6}>
      <EntryMenuItems capabilities={capabilities} entry={entry} onAction={guard.onAction} platform={platform} surface="dropdown" />
    </DropdownMenuContent>
  </DropdownMenu>;
}

/** One shared cache feeds breadcrumb menus and tree rows for this mounted root. */
export function useFileNavigation({ source, actions, state, onStateChange, onOpenFile, path, onError }: {
  source: FileSource; actions?: FileActions; state: FileViewerState; onStateChange: FileViewerProps["onStateChange"];
  onOpenFile: ViewerHost["navigation"]["openFile"]; path: string | null; onError?: FileViewerProps["onError"];
}) {
  const [cache, setCache] = useState<{ id: string; listings: Record<string, readonly FileEntry[]>; revision: number }>({ id: source.id, listings: {}, revision: 0 });
  const listings = cache.id === source.id ? cache.listings : {};
  const revision = cache.id === source.id ? cache.revision : 0;
  const [renaming, setRenaming] = useState<{ sourceId: string; path: string } | null>(null);
  const [editing, setEditing] = useState<{ sourceId: string; edit: TreeEdit } | null>(null);
  const requests = useRef(new Map<string, AbortController>());
  const searches = useRef(new Set<AbortController>());
  const mutations = useRef(new Set<AbortController>());
  const current = useRef({ state, onStateChange, source, onError, listings, path, onOpenFile });
  current.current = { state, onStateChange, source, onError, listings, path, onOpenFile };
  const report = useCallback((error: unknown) => current.current.onError?.(new Error(errorMessage(error))), []);
  const load = useCallback((directory: string) => {
    if (!source.list || requests.current.has(directory)) return;
    const controller = new AbortController();
    requests.current.set(directory, controller);
    void source.list(directory, { signal: controller.signal }).then((entries) => {
      if (!controller.signal.aborted && current.current.source === source) {
        setCache((previous) => ({ id: source.id, listings: { ...(previous.id === source.id ? previous.listings : {}), [directory]: entries }, revision: previous.id === source.id ? previous.revision : 0 }));
      }
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) report(error);
    }).finally(() => { if (requests.current.get(directory) === controller) requests.current.delete(directory); });
  }, [source, report]);
  useEffect(() => () => {
    for (const controller of requests.current.values()) controller.abort();
    requests.current.clear();
    for (const controller of searches.current) controller.abort();
    searches.current.clear();
    for (const controller of mutations.current) controller.abort();
    mutations.current.clear();
  }, [source]);
  useEffect(() => {
    // Expanded folders outlive a mounted tab through the host's view state.
    // Restore their listings even when the active file has no such ancestors.
    for (const directory of current.current.state.expandedDirectories ?? []) load(directory);
  }, [source, load]);
  const reconcile = useCallback((changes: readonly FileChange[]) => {
    if (current.current.source !== source) return;
    // The first catalog may arrive while the first root listing is awaiting
    // it. Keep pending directories too, or that abort leaves "Reading…" forever.
    const before = current.current;
    const next = reconcileFileTree(before.listings, before.state.expandedDirectories ?? [], changes);
    const directories = new Set([...Object.keys(next.listings), ...next.expanded, ...requests.current.keys()]);
    for (const controller of requests.current.values()) controller.abort();
    requests.current.clear();
    for (const controller of searches.current) controller.abort();
    searches.current.clear();
    // Keep the visible tree until fresh listings arrive. Clearing it first
    // erases the tree's knowledge of which open directories need reloading.
    for (const directory of directories) {
      if (!changes.some(change => change.kind === "deleted" && (directory === change.path || directory.startsWith(`${change.path}/`)))
        && !changes.some(change => change.kind === "moved" && (directory === change.from || directory.startsWith(`${change.from}/`)))) load(directory);
    }
    setCache((previous) => ({ id: source.id, listings: reconcileFileTree(previous.id === source.id ? previous.listings : {}, [], changes).listings,
      revision: (previous.id === source.id ? previous.revision : 0) + 1 }));
    if (JSON.stringify(next.expanded) !== JSON.stringify(before.state.expandedDirectories ?? [])) before.onStateChange({ ...before.state, expandedDirectories: next.expanded });
    let moved = before.path;
    for (const change of changes) if (moved !== null && change.kind === "moved") moved = movedFilePath(moved, change.from, change.to);
    // The file moved under the view: the same file, so whatever panel is open stays open.
    if (moved !== before.path && moved !== null) before.onOpenFile(moved, { target: "current", panel: before.state.panel ?? undefined });
  }, [source, load]);
  useEffect(() => source.subscribe?.(change => { if (change.sourceId === source.id) reconcile(change.changes); }), [source, reconcile]);

  const expanded = useMemo(() => new Set(state.expandedDirectories ?? []), [state.expandedDirectories]);
  const setExpanded = useCallback((update: (previous: ReadonlySet<string>) => ReadonlySet<string>) => {
    const { state: previous, onStateChange: change } = current.current;
    const before = new Set(previous.expandedDirectories ?? []);
    const next = update(before);
    if (before.size === next.size && [...before].every((directory) => next.has(directory))) return;
    change({ ...previous, expandedDirectories: [...next] });
  }, []);
  const capabilities = useMemo(() => {
    const available = new Set<EntryAction>(["open"]);
    for (const action of Object.keys(actions?.perform ?? {})) available.add(action as EntryAction);
    if (source.rename) available.add("rename");
    if (source.create) { available.add("new-file"); available.add("new-folder"); }
    if (source.trash) available.add("trash");
    if (source.duplicate) available.add("duplicate");
    return available;
  }, [source, actions]);
  const askTree = useCallback((request: TreeEditRequest) => {
    const { state: previous, onStateChange: change } = current.current;
    change({ ...previous, panel: "tree" });
    setEditing((previous) => ({ sourceId: current.current.source.id, edit: { ...request, nonce: (previous?.edit.nonce ?? 0) + 1 } }));
  }, []);
  const mutate = useCallback(async (operation: (signal: AbortSignal) => Promise<FileMutationResult>) => {
    const controller = new AbortController();
    mutations.current.add(controller);
    try {
      const result = await operation(controller.signal);
      if (controller.signal.aborted || current.current.source !== source) return null;
      if (result.status === "failed") { report(new Error(result.message)); return null; }
      if (result.status !== "committed") return null;
      reconcile([result.change]);
      return result.path;
    } catch (error) { if (!controller.signal.aborted && current.current.source === source) report(error); return null; }
    finally { mutations.current.delete(controller); }
  }, [source, reconcile, report]);
  const rename = useCallback((entry: MenuEntryTarget, name: string) => mutate(signal => source.rename!(entry.path, { name, signal })), [source, mutate]);
  const create = useCallback(async (directory: string, kind: "file" | "directory", name: string) => {
    try {
      const created = await mutate(signal => source.create!(directory, { kind, name, signal }));
      if (created !== null && current.current.source === source) { load(directory); if (kind === "file") onOpenFile(created, { target: "new", panel: FILE_PANEL_TREE }); }
      return created;
    } catch (error) { report(error); return null; }
  }, [source, load, onOpenFile, report, mutate]);
  const trash = useCallback(async (entry: MenuEntryTarget) => {
    try { const trashed = await mutate(signal => source.trash!(entry.path, { signal })); if (trashed !== null && current.current.source === source) load(parentOf(entry.path)); return trashed !== null; }
    catch (error) { if (current.current.source === source) report(error); return false; }
  }, [source, load, report, mutate]);
  const onAction = useCallback<MenuAction>((action, entry) => {
    if (action === "open") onOpenFile(entry.path, entry.surface === "crumb" ? { target: "new" } : { target: "new", panel: FILE_PANEL_TREE });
    else if (action === "rename") {
      if (entry.path === path && entry.surface === "crumb" && path !== null) setRenaming({ sourceId: source.id, path });
      else askTree({ mode: "rename", entry });
    } else if (action === "new-file" || action === "new-folder") askTree({ mode: "create", directory: entry.path, kind: action === "new-file" ? "file" : "directory" });
    else if (action === "trash") void trash(entry);
    else if (action === "duplicate") void mutate(signal => source.duplicate!(entry.path, { signal }));
    else void Promise.resolve(actions?.perform?.[action]?.(entry)).catch(report);
  }, [source, actions, path, onOpenFile, askTree, trash, report, mutate]);
  const platform = actions?.platform ?? "linux";
  const paths = useCallback(async () => {
    const controller = new AbortController();
    searches.current.add(controller);
    try { const paths = await source.paths?.({ signal: controller.signal }) ?? []; return !controller.signal.aborted && current.current.source === source ? paths : []; }
    catch (error) { if (!controller.signal.aborted) report(error); return []; }
    finally { searches.current.delete(controller); }
  }, [source, report]);
  const tree: FileTreeSource = { rootName: source.rootName, expanded, setExpanded, listings, load, revision, paths, platform, capabilities, onAction,
    rename: source.rename ? rename : undefined, create: source.create ? create : undefined, trash: source.trash ? trash : undefined };
  const crumbs: CrumbSource = {
    useListing(directory) {
      const listed = listings[directory];
      useEffect(() => { if (listed === undefined) load(directory); }, [directory, listed]);
      return listed ?? null;
    },
    wrapCrumb: ({ crumb, children }) => <EntryContextMenu capabilities={capabilities} entry={{ path: crumb.path, kind: crumb.kind === "file" ? "file" : "directory", surface: "crumb" }} onAction={onAction} platform={platform}>{children}</EntryContextMenu>,
    renderCrumbActions: ({ crumb }) => <CrumbActions entry={{ path: crumb.path, kind: "file", surface: "crumb" }} capabilities={capabilities} platform={platform} onAction={onAction} />,
    renderRename: ({ crumb }) => renaming?.sourceId === source.id && renaming.path === path && path !== null ? <InlineName initial={crumb.label} kind="file" label="Rename file" className="max-w-64" onCancel={() => setRenaming(null)} onCommit={async (name) => {
      const renamed = await rename({ path: crumb.path, kind: "file" }, name);
      if (renamed !== null) setRenaming(previous => previous?.sourceId === source.id && previous.path === crumb.path ? null : previous);
      return renamed !== null;
    }} /> : null,
  };
  return { tree, crumbs, edit: editing?.sourceId === source.id ? editing.edit : null };
}
