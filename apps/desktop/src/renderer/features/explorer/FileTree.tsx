import { ChevronDown, ChevronRight, Search, X } from "lucide-react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ContextMenu, ContextMenuContent, ContextMenuTrigger } from "@renderer/components/ui/context-menu";
import { isMac } from "@renderer/lib/platform";
import { cn } from "@renderer/lib/utils";
import { useExplorer, useTree } from "@renderer/state/explorer";
import type { DirEntry } from "@shared/ipc/explorer";
import type { ExplorerRoot } from "@shared/types";

import { EntryMenuItems, useMenuFocusGuard } from "./EntryContextMenu";
import { createEntry, currentPlatform, renameEntry, trashEntry, type EntryActionContext } from "./entry-actions";
import type { MenuEntryTarget } from "./entry-menu";
import { FileIcon, FolderIcon } from "cad-viewer/shell";
import { fuzzyFilter } from "./fuzzy";
import { InlineName } from "./InlineName";

/**
 * The file tab's right-hand tree (Codex's layout: content left, tree right).
 *
 * Lazy: a directory's children are fetched when it is first expanded and kept
 * afterwards. A recursive read of a repository with `node_modules` in it costs
 * seconds and megabytes for a pane that shows thirty rows.
 *
 * The filter is a different view of the same directory, not a filter over the
 * tree: typing switches to a flat, fuzzy-ranked list of every path under the
 * root, because "find the file called x" and "see where x lives" are different
 * questions and the tree only answers the second one well.
 *
 * Every row has the entry menu (`EntryContextMenu.tsx`) on right-click, and
 * the two items that need a field — Rename, New file/folder — draw it in
 * the row (`InlineName`). The keyboard has the same two: F2 renames the
 * cursor row, ⌘⌫ (Ctrl+Delete) moves it to the trash.
 */

const ROW_HEIGHT = 28;
const INDENT = 12;

type Row = {
  path: string;
  name: string;
  kind: "file" | "directory";
  depth: number;
  expanded: boolean;
};

/** The one inline field the tree can show: a rename over a row, or a new entry in a folder. */
export type TreeEditRequest =
  | { mode: "rename"; entry: MenuEntryTarget }
  | { mode: "create"; directory: string; kind: "file" | "directory" };
type Editing = TreeEditRequest;

/**
 * An edit asked for from outside — a crumb's `Rename` or `New folder`
 * (`FileTab`). The nonce makes asking twice two requests.
 */
export type TreeEdit = TreeEditRequest & { nonce: number };

export function FileTree({
  projectId,
  root,
  projectName,
  activePath,
  reveal = null,
  edit = null,
  onOpen,
  fsRevision,
}: {
  projectId: string;
  /** The directory listed: null for the project, else one of its worktrees (plan §9). */
  root: ExplorerRoot;
  projectName: string;
  /** The file the tab is showing, highlighted in the tree. */
  activePath: string | null;
  /**
   * A path to expand to and select without opening it — an agent's `reveal`
   * (src/renderer/state/explorer.ts). Wins over `activePath` for the reveal
   * and the scroll; the open file stays highlighted too.
   */
  reveal?: { path: string; directory: boolean; root: ExplorerRoot } | null;
  /** A rename or a create the breadcrumb asked for; drawn as if from the row's own menu. */
  edit?: TreeEdit | null;
  onOpen: (path: string) => void;
  /** Bumped by `files.changed`; re-reads whatever is currently expanded. */
  fsRevision: number;
}) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [editing, setEditing] = useState<Editing | null>(null);
  /** The row the context menu is aimed at; the root when the empty space was clicked. */
  const [menuTarget, setMenuTarget] = useState<MenuEntryTarget>({ path: "", kind: "directory" });
  const listRef = useRef<HTMLDivElement | null>(null);

  /**
   * Which folders are open, and what is in them. One set, one cache, and both
   * in the store rather than in this component.
   *
   * They used to be local state, and "which folders are open" used to be an
   * *override map* over a default derived from the open file. Both halves of
   * that were wrong, and together they are why expanding a folder two levels
   * down did nothing:
   *
   * - The component is remounted whenever another tab is selected, and opening
   *   a file *makes a tab* — so the three levels a person had just expanded to
   *   reach a file were thrown away by the click that opened it.
   * - In the tree that came back, the ancestors of the open file were "open"
   *   by derivation with no entry in the override map, so a click on one read
   *   `opening = !isExpanded(dir)` as `false`, wrote "closed" and issued no
   *   `explorer.list`. Clicking the folders again collapsed the tree instead
   *   of opening them.
   *
   * One set, written by the person and by `reveal` alike, says both things
   * without disagreeing with itself.
   */
  const { open: expanded, listings: children } = useTree(root);
  const setTreeOpen = useExplorer((state) => state.setTreeOpen);
  const setTreeListing = useExplorer((state) => state.setTreeListing);
  const setExpanded = useCallback(
    (next: (current: ReadonlySet<string>) => ReadonlySet<string>) => setTreeOpen(root, next),
    [root, setTreeOpen],
  );
  const setListing = useCallback(
    (directory: string, entries: DirEntry[]) => setTreeListing(root, directory, entries),
    [root, setTreeListing],
  );
  // The request every read here makes: the project, and the root within it.
  const at = useMemo(() => ({ projectId, ...(root ? { root } : {}) }), [projectId, root]);

  // A reveal into another root's tree is not this tree's business.
  const revealTarget = (reveal && reveal.root === root ? reveal.path : null) ?? activePath;
  const revealed = useMemo(() => {
    if (!revealTarget) {
      return new Set<string>();
    }
    // A revealed folder is opened as well as shown; a file only its ancestors.
    const parts = revealTarget.split("/");
    const segments = reveal?.directory && reveal.root === root && reveal.path === revealTarget ? parts : parts.slice(0, -1);
    return new Set(segments.map((_, index) => segments.slice(0, index + 1).join("/")));
  }, [revealTarget, reveal, root]);

  const isExpanded = useCallback((directory: string) => expanded.has(directory), [expanded]);

  /**
   * Read one directory's children.
   *
   * A promise chain rather than `async`/`await`: the state is set from a
   * callback, which is the shape that says "this is an answer arriving", and
   * the shape React's rules can see. The same code written with `await` reads
   * to a linter as a synchronous setState inside whichever effect called it.
   */
  const load = useCallback(
    (directory: string) =>
      window.hardcore.explorer
        .list({ ...at, path: directory })
        .then((entries: DirEntry[]) => setListing(directory, entries))
        .catch(() => {}),
    [at, setListing],
  );

  // The root, on every mount: the listings survive a remount, but a tree that
  // trusted a cache taken before the last `git checkout` would show files that
  // are not there.
  useEffect(() => {
    void load("");
  }, [load]);

  /**
   * The watcher fired: re-read every directory that is currently open.
   *
   * A store subscription rather than an effect over `fsRevision`, because it
   * is a reaction to an event. `expanded` is read at that moment from the ref
   * below; as an effect dependency it would re-read the whole open tree every
   * time a folder was expanded.
   */
  const openDirectories = useMemo(
    () => Object.keys(children).filter((directory) => isExpanded(directory)),
    [children, isExpanded],
  );
  const openRef = useRef(openDirectories);
  useEffect(() => {
    openRef.current = openDirectories;
  }, [openDirectories]);

  useEffect(
    () =>
      useExplorer.subscribe((state, previous) => {
        // A batch from another root's watcher changed another tree.
        if (state.fsRevision !== previous.fsRevision && state.changedRoot === root) {
          for (const directory of openRef.current) {
            void load(directory);
          }
        }
      }),
    [load, root],
  );

  /**
   * The flat corpus behind the filter, fetched on the first keystroke and
   * again whenever the filesystem has moved on since it was taken.
   *
   * Stamped with the revision it was read at rather than cleared by the
   * watcher: clearing is a synchronous setState in an effect, and the stamp
   * says the same thing without one.
   */
  const [corpus, setCorpus] = useState<{ revision: number; paths: string[] } | null>(null);
  const filtering = query.trim() !== "";
  const corpusStale = corpus === null || corpus.revision !== fsRevision;

  useEffect(() => {
    if (!filtering || !corpusStale) {
      return;
    }
    let cancelled = false;
    void window.hardcore.explorer
      .paths({ ...at, path: "" })
      .then((result) => {
        if (!cancelled) {
          setCorpus({ revision: fsRevision, paths: result.paths });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCorpus({ revision: fsRevision, paths: [] });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [filtering, corpusStale, fsRevision, at]);

  /**
   * Reveal: open every ancestor of the revealed path and read them.
   *
   * `setExpanded` returns the set it was given when there is nothing to add,
   * which is the common case — the ancestors of the file already open — and
   * React drops an update that returns the same value, so this costs a render
   * only when the tree actually has to move.
   *
   * A folder the person shut by hand does spring back when a file inside it is
   * opened afterwards. That is the point of a reveal: the alternative is a
   * tree that selects a row it is not showing.
   */
  useEffect(() => {
    if (revealed.size > 0) {
      setExpanded((current) =>
        [...revealed].every((directory) => current.has(directory))
          ? current
          : new Set([...current, ...revealed]),
      );
    }
    for (const directory of revealed) {
      void load(directory);
    }
  }, [revealed, load, setExpanded]);

  /**
   * Scroll the open file into view.
   *
   * By `data-path` rather than through a map of row refs: the rows are a list
   * that changes shape on every expansion, and a ref callback per row that
   * writes into a shared map is a ref read during render.
   */
  useEffect(() => {
    if (!revealTarget) {
      return;
    }
    listRef.current
      ?.querySelector(`[data-path="${CSS.escape(revealTarget)}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [revealTarget, children]);

  /**
   * Open or shut one folder — always the opposite of what is on screen, and
   * always a read when it opens, because a folder can be open with its
   * children still unknown (a reveal, or a listing that failed).
   */
  const toggle = useCallback(
    (directory: string) => {
      const opening = !expanded.has(directory);
      setExpanded((current) => {
        const next = new Set(current);
        if (opening) {
          next.add(directory);
        } else {
          next.delete(directory);
        }
        return next;
      });
      if (opening) {
        void load(directory);
      }
    },
    [expanded, load, setExpanded],
  );

  /**
   * The entry menu's context: what the tree draws for the two items that
   * need a field, and where everything else goes (`entry-actions.ts`).
   * `beginCreate` opens the folder first — a field inside a shut folder is
   * a field nobody can see.
   */
  const ctx = useMemo<EntryActionContext>(
    () => ({
      projectId,
      root,
      platform: currentPlatform(),
      beginRename: (entry) => setEditing({ mode: "rename", entry }),
      beginCreate: (directory, kind) => {
        if (directory !== "" && !expanded.has(directory)) {
          setExpanded((current) => new Set([...current, directory]));
          void load(directory);
        }
        setEditing({ mode: "create", directory, kind });
      },
    }),
    [projectId, root, expanded, setExpanded, load],
  );
  const menuGuard = useMenuFocusGuard(ctx);

  /**
   * A crumb asked for an edit. The folders above it are opened and read
   * first — a field in a folder the tree has shut is a field nobody sees —
   * and the request is honoured once per nonce.
   */
  const honoured = useRef<number>(0);
  useEffect(() => {
    if (!edit || edit.nonce === honoured.current) {
      return;
    }
    honoured.current = edit.nonce;
    const target = edit.mode === "rename" ? edit.entry.path : edit.directory;
    const segments = target === "" ? [] : target.split("/");
    const ancestors = segments.slice(0, edit.mode === "rename" ? -1 : undefined).map((_, index, all) => all.slice(0, index + 1).join("/"));
    if (ancestors.length > 0) {
      setExpanded((current) =>
        ancestors.every((directory) => current.has(directory)) ? current : new Set([...current, ...ancestors]),
      );
      for (const directory of ancestors) {
        void load(directory);
      }
    }
    setQuery("");
    setEditing(edit.mode === "rename" ? { mode: "rename", entry: edit.entry } : { mode: "create", directory: edit.directory, kind: edit.kind });
  }, [edit, setExpanded, load]);

  /**
   * When an inline field goes away the focus goes with it — to `body` —
   * and the next F2 or arrow key would be lost. The list takes it back, so
   * a rename from the keyboard ends where it began.
   */
  const wasEditing = useRef(false);
  useEffect(() => {
    if (wasEditing.current && editing === null) {
      listRef.current?.focus();
    }
    wasEditing.current = editing !== null;
  }, [editing]);

  /** The visible rows, flattened depth-first from what is expanded. */
  const rows = useMemo<Row[]>(() => {
    const out: Row[] = [];
    const walk = (directory: string, depth: number) => {
      for (const entry of children[directory] ?? []) {
        const open = entry.kind === "directory" && isExpanded(entry.path);
        out.push({
          path: entry.path,
          name: entry.name,
          kind: entry.kind,
          depth,
          expanded: open,
        });
        if (open) {
          walk(entry.path, depth + 1);
        }
      }
    };
    walk("", 0);
    return out;
  }, [children, isExpanded]);

  /** Where the "new entry" field goes: first among its folder's children. */
  const creatingAt = useMemo(() => {
    if (editing?.mode !== "create") {
      return -1;
    }
    if (editing.directory === "") {
      return 0;
    }
    const at = rows.findIndex((row) => row.path === editing.directory);
    return at < 0 ? -1 : at + 1;
  }, [editing, rows]);
  const creatingDepth =
    editing?.mode === "create" && editing.directory !== ""
      ? (rows.find((row) => row.path === editing.directory)?.depth ?? 0) + 1
      : 0;

  const matches = useMemo(
    () => (filtering ? fuzzyFilter(corpus?.paths ?? [], query, 200) : []),
    [corpus, filtering, query],
  );

  const visible = filtering ? matches.map((match) => match.path) : rows.map((row) => row.path);

  // A cursor that has scrolled out of the list is worse than none: arrow keys
  // would move a selection nobody can see.
  const cursorPath = cursor && visible.includes(cursor) ? cursor : (visible[0] ?? null);

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (visible.length === 0) {
      return;
    }
    const at = cursorPath ? visible.indexOf(cursorPath) : -1;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor(visible[Math.min(at + 1, visible.length - 1)] ?? null);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor(visible[Math.max(at - 1, 0)] ?? null);
      return;
    }
    if (!cursorPath) {
      return;
    }
    const row = rows.find((candidate) => candidate.path === cursorPath);
    // The two edits the menu offers, from the keyboard: F2 and ⌘⌫ (Ctrl+Delete).
    if (row && event.key === "F2") {
      event.preventDefault();
      setEditing({ mode: "rename", entry: { path: row.path, kind: row.kind } });
      return;
    }
    if (
      row &&
      (event.key === "Backspace" || event.key === "Delete") &&
      (isMac ? event.metaKey : event.ctrlKey) &&
      !event.altKey &&
      !event.shiftKey
    ) {
      event.preventDefault();
      void trashEntry({ path: row.path, kind: row.kind }, ctx);
      return;
    }
    if (event.key === "ArrowRight" && row?.kind === "directory" && !row.expanded) {
      event.preventDefault();
      toggle(cursorPath);
      return;
    }
    if (event.key === "ArrowLeft" && row?.kind === "directory" && row.expanded) {
      event.preventDefault();
      toggle(cursorPath);
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      if (row?.kind === "directory") {
        toggle(cursorPath);
      } else {
        onOpen(cursorPath);
      }
    }
  };

  /**
   * Aim the menu. A row's `onContextMenu` runs before the list's — the
   * trigger — sees the same event, so the target is set by the time Radix
   * opens the menu; the empty space under the rows is the root.
   */
  const aim = (event: React.MouseEvent) => {
    const row = (event.target as HTMLElement).closest<HTMLElement>("[data-path]");
    const path = row?.dataset.path ?? "";
    const kind = row?.dataset.kind === "file" ? "file" : "directory";
    setMenuTarget({ path, kind });
    if (row && path) {
      setCursor(path);
    }
  };

  const finishRename = async (entry: MenuEntryTarget, name: string) => {
    const renamed = await renameEntry(entry, name, ctx);
    if (renamed !== null) {
      setCursor(renamed);
      setEditing(null);
    }
    return renamed !== null;
  };

  const finishCreate = async (directory: string, kind: "file" | "directory", name: string) => {
    const created = await createEntry(directory, kind, name, ctx);
    if (created !== null) {
      setCursor(created);
      setEditing(null);
    }
    return created !== null;
  };

  const newEntryRow =
    editing?.mode === "create" ? (
      <div
        className="flex w-full items-center gap-1.5 pr-2"
        key="__new__"
        style={{ height: ROW_HEIGHT, paddingLeft: 6 + creatingDepth * INDENT }}
      >
        <span className="w-3 shrink-0" />
        {editing.kind === "directory" ? (
          <FolderIcon className="size-3.5 shrink-0 text-muted-foreground" open={false} />
        ) : (
          <FileIcon className="size-3.5 shrink-0 text-muted-foreground" path="" />
        )}
        <InlineName
          initial=""
          kind={editing.kind}
          label={editing.kind === "directory" ? "New folder name" : "New file name"}
          onCancel={() => setEditing(null)}
          onCommit={(name) => finishCreate(editing.directory, editing.kind, name)}
          placeholder={editing.kind === "directory" ? "Folder name" : "File name"}
        />
      </div>
    ) : null;

  return (
    <div className="flex h-full min-h-0 flex-col bg-sidebar/40">
      <div className="flex h-9 shrink-0 items-center gap-1 border-b px-2">
        <div className="relative flex min-w-0 flex-1 items-center">
          <Search className="pointer-events-none absolute left-2 size-3 text-muted-foreground" />
          <input
            aria-label="Filter files"
            className="h-6 w-full min-w-0 rounded-md bg-transparent pr-5 pl-6.5 text-[12px] outline-none placeholder:text-muted-foreground focus:bg-background/70"
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Filter files…"
            spellCheck={false}
            value={query}
          />
          {query !== "" ? (
            <button
              aria-label="Clear filter"
              className="absolute right-1 flex size-4 items-center justify-center rounded-sm text-muted-foreground hover:bg-accent"
              onClick={() => setQuery("")}
              type="button"
            >
              <X className="size-2.5" />
            </button>
          ) : null}
        </div>
      </div>

      <ContextMenu modal={false}>
        <ContextMenuTrigger asChild>
          <div
            className="min-h-0 flex-1 overflow-auto py-1 outline-none"
            onContextMenu={aim}
            onKeyDown={onKeyDown}
            ref={listRef}
            role="tree"
            tabIndex={0}
          >
            {filtering ? (
              matches.length === 0 ? (
                <p className="px-3 py-6 text-center text-xs text-muted-foreground">
                  {corpus === null ? "Searching…" : `No file matches “${query.trim()}”`}
                </p>
              ) : (
                matches.map((match) => (
                  <FilterRow
                    active={match.path === activePath || match.path === reveal?.path}
                    cursor={match.path === cursorPath}
                    indices={match.indices}
                    key={match.path}
                    onOpen={() => onOpen(match.path)}
                    path={match.path}
                  />
                ))
              )
            ) : rows.length === 0 && !newEntryRow ? (
              <p className="px-3 py-6 text-center text-xs text-muted-foreground">
                {children[""] === undefined ? "Reading…" : `${projectName} is empty`}
              </p>
            ) : (
              <>
                {creatingAt === 0 ? newEntryRow : null}
                {rows.map((row, index) => (
                  <Fragment key={row.path}>
                    <TreeRow
                      active={row.path === activePath || row.path === reveal?.path}
                      cursor={row.path === cursorPath}
                      onRename={
                        editing?.mode === "rename" && editing.entry.path === row.path
                          ? {
                              commit: (name) => finishRename(editing.entry, name),
                              cancel: () => setEditing(null),
                            }
                          : null
                      }
                      onSelect={() => {
                        setCursor(row.path);
                        if (row.kind === "directory") {
                          toggle(row.path);
                        } else {
                          onOpen(row.path);
                        }
                      }}
                      row={row}
                    />
                    {creatingAt === index + 1 ? newEntryRow : null}
                  </Fragment>
                ))}
              </>
            )}
          </div>
        </ContextMenuTrigger>
        <ContextMenuContent className="w-56" data-entry-menu={menuTarget.path} onCloseAutoFocus={menuGuard.onCloseAutoFocus}>
          <EntryMenuItems ctx={menuGuard.ctx} entry={menuTarget} />
        </ContextMenuContent>
      </ContextMenu>
    </div>
  );
}

function TreeRow({
  row,
  active,
  cursor,
  onSelect,
  onRename,
}: {
  row: Row;
  active: boolean;
  cursor: boolean;
  onSelect: () => void;
  /** Set while this row is being renamed: the name becomes a field. */
  onRename: { commit: (name: string) => Promise<boolean>; cancel: () => void } | null;
}) {
  const icon =
    row.kind === "directory" ? (
      <FolderIcon className="size-3.5 shrink-0 text-muted-foreground" open={row.expanded} />
    ) : (
      <FileIcon className="size-3.5 shrink-0 text-muted-foreground" path={row.path} />
    );
  const chevron =
    row.kind === "directory" ? (
      row.expanded ? (
        <ChevronDown className="size-3 shrink-0 text-muted-foreground" />
      ) : (
        <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
      )
    ) : (
      <span className="w-3 shrink-0" />
    );

  if (onRename) {
    return (
      <div
        className="flex w-full items-center gap-1.5 pr-2"
        data-kind={row.kind}
        data-path={row.path}
        style={{ height: ROW_HEIGHT, paddingLeft: 6 + row.depth * INDENT }}
      >
        {chevron}
        {icon}
        <InlineName
          initial={row.name}
          kind={row.kind}
          label={`Rename ${row.name}`}
          onCancel={onRename.cancel}
          onCommit={onRename.commit}
        />
      </div>
    );
  }

  return (
    <button
      aria-expanded={row.kind === "directory" ? row.expanded : undefined}
      aria-selected={active}
      className={cn(
        "flex w-full items-center gap-1.5 rounded-md pr-2 text-left text-[13px] transition-colors",
        active
          ? "bg-accent font-medium text-accent-foreground"
          : "text-foreground/80 hover:bg-accent/50",
        cursor && !active && "bg-accent/30",
      )}
      data-kind={row.kind}
      data-path={row.path}
      onClick={onSelect}
      role="treeitem"
      style={{ height: ROW_HEIGHT, paddingLeft: 6 + row.depth * INDENT }}
      title={row.path}
      type="button"
    >
      {chevron}
      {icon}
      <span className="truncate">{row.name}</span>
    </button>
  );
}

function FilterRow({
  path,
  indices,
  active,
  cursor,
  onOpen,
}: {
  path: string;
  indices: number[];
  active: boolean;
  cursor: boolean;
  onOpen: () => void;
}) {
  const lastSlash = path.lastIndexOf("/");
  const directory = lastSlash < 0 ? "" : path.slice(0, lastSlash + 1);
  return (
    <button
      aria-selected={active}
      className={cn(
        "flex w-full items-center gap-1.5 rounded-md px-2 text-left text-[13px] transition-colors",
        active
          ? "bg-accent font-medium text-accent-foreground"
          : "text-foreground/80 hover:bg-accent/50",
        cursor && !active && "bg-accent/30",
      )}
      data-kind="file"
      data-path={path}
      onClick={onOpen}
      role="option"
      style={{ height: ROW_HEIGHT }}
      title={path}
      type="button"
    >
      <FileIcon className="size-3.5 shrink-0 text-muted-foreground" path={path} />
      <span className="truncate">
        {directory ? <span className="text-muted-foreground">{directory}</span> : null}
        <Highlight from={directory.length} indices={indices} text={path.slice(directory.length)} />
      </span>
    </button>
  );
}

/** The matched characters, bolded. The reason `fuzzyMatch` returns indices. */
function Highlight({
  text,
  indices,
  from,
}: {
  text: string;
  indices: number[];
  from: number;
}) {
  const hits = new Set(indices.map((index) => index - from));
  return (
    <>
      {[...text].map((character, index) =>
        hits.has(index) ? (
          <span className="font-semibold text-foreground" key={index}>
            {character}
          </span>
        ) : (
          <span key={index}>{character}</span>
        ),
      )}
    </>
  );
}
