import { ChevronDown, ChevronRight, Search, X } from "lucide-react";
import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ContextMenu, ContextMenuContent, ContextMenuTrigger } from "@/components/ui/context-menu";
import { cn } from "@/ui/utils";

import { EntryMenuItems, useEntryMenuFocusGuard } from "./EntryMenu.jsx";
import { ALL_ENTRY_CAPABILITIES } from "./entry-menu.js";
import { fuzzyFilter } from "./fuzzy.js";
import { FileIcon, FolderIcon } from "./icons.jsx";
import { InlineName } from "./InlineName.jsx";

/**
 * The file surface's tree — the rightmost panel in the nav row's list, in
 * BOTH apps (`panels.js`).
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
 * Every row has the entry menu (`EntryMenu.jsx`) on right-click, filtered by
 * what the host can actually do, and the two items that need a field — Rename,
 * New file/folder — draw it in the row (`InlineName`). The keyboard has the
 * same two: F2 renames the cursor row, ⌘⌫ (Ctrl+Delete) moves it to the trash.
 * Both are capabilities, so in a browser tab neither key does anything and
 * neither item is in the menu.
 *
 * ## The source adapter
 *
 * Where a listing comes from is the one thing the two hosts do not share, so
 * it is a prop rather than an import — the same shape `Breadcrumbs.jsx` takes,
 * for the same reason. The desktop reads a directory at a time over IPC with
 * gitignore semantics and a watcher behind it; the standalone viewer walks the
 * catalog directory tree it already holds in memory
 * (`catalogTreeSource.js`), so its tree shows the CAD files the catalog knows
 * and the directories containing them. That is the honest web subset and the
 * one place the two trees legitimately differ in CONTENT — the rows, the
 * glyphs, the indentation, the expand/collapse, the keyboard and the filter
 * box are this file, and are the same in both.
 *
 * @typedef {object} TreeEntry
 * @property {string} path Root-relative.
 * @property {string} name
 * @property {"file"|"directory"} kind
 *
 * @typedef {object} FileTreeSource
 * @property {string} rootName Named in the "… is empty" line.
 * @property {ReadonlySet<string>} expanded Which directories are open.
 * @property {(update: (current: ReadonlySet<string>) => ReadonlySet<string>) => void} setExpanded
 * @property {Record<string, readonly TreeEntry[]>} listings
 *   Directory id to its entries. A directory absent from this map has not been
 *   read yet; `""` absent is the whole tree still loading.
 * @property {(directory: string) => void} load
 *   Ask for one directory's entries. Called on mount for the root, on every
 *   expansion, on every reveal, and for the open directories when `revision`
 *   moves. A host that holds everything already may make it a no-op.
 * @property {number} revision
 *   Bumped when the filesystem — or the catalog — has moved on. Re-reads
 *   whatever is currently expanded, and retires the filter's corpus.
 * @property {() => Promise<readonly string[]>} paths
 *   Every file path under the root, flat: the corpus the filter ranks. Fetched
 *   on the first keystroke, not before.
 * @property {import("./entry-menu.js").Platform} platform
 * @property {ReadonlySet<import("./entry-menu.js").EntryAction>} [capabilities]
 * @property {(action: import("./entry-menu.js").EntryAction, entry: import("./entry-menu.js").MenuEntryTarget) => void} onAction
 *   Everything the menu offers EXCEPT the three that start an inline field:
 *   the tree draws that field itself and finishes it through `rename` /
 *   `create` below, because a field belongs to the row it is in.
 * @property {(entry: import("./entry-menu.js").MenuEntryTarget, name: string) => Promise<string|null>} [rename]
 *   The new path, or null to keep the field up so the name can be fixed.
 * @property {(directory: string, kind: "file"|"directory", name: string) => Promise<string|null>} [create]
 * @property {(entry: import("./entry-menu.js").MenuEntryTarget) => Promise<boolean>} [trash]
 */

const ROW_HEIGHT = 28;
const INDENT = 12;

/**
 * The one inline field the tree can show: a rename over a row, or a new entry
 * in a folder. An edit asked for from OUTSIDE — a crumb's `Rename` or `New
 * folder` — arrives as the same thing plus a nonce, so asking twice is two
 * requests.
 *
 * @typedef {{ mode: "rename", entry: import("./entry-menu.js").MenuEntryTarget }
 *   | { mode: "create", directory: string, kind: "file"|"directory" }} TreeEditRequest
 * @typedef {TreeEditRequest & { nonce: number }} TreeEdit
 */

/**
 * @param {object} props
 * @param {FileTreeSource} props.source
 * @param {string|null} props.activePath The file the surface is showing, highlighted in the tree.
 * @param {{ path: string, directory: boolean }|null} [props.reveal]
 *   A path to expand to and select without opening it. Wins over `activePath`
 *   for the reveal and the scroll; the open file stays highlighted too.
 * @param {TreeEdit|null} [props.edit] A rename or a create the breadcrumb asked for.
 * @param {(path: string) => void} props.onOpen
 */
export function FileTree({ source, activePath, reveal = null, edit = null, onOpen }) {
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(null);
  /** @type {[TreeEditRequest|null, Function]} */
  const [editing, setEditing] = useState(null);
  /** The row the context menu is aimed at; the root when the empty space was clicked. */
  const [menuTarget, setMenuTarget] = useState({ path: "", kind: "directory" });
  const listRef = useRef(null);

  const {
    rootName,
    expanded,
    setExpanded,
    listings: children,
    load,
    revision,
    paths,
    platform,
    capabilities = ALL_ENTRY_CAPABILITIES
  } = source;

  // A reveal is answered by whichever tree is on screen; the host decides
  // whether one aimed elsewhere reaches this one at all.
  const revealTarget = reveal?.path ?? activePath;
  const revealed = useMemo(() => {
    if (!revealTarget) {
      return new Set();
    }
    // A revealed folder is opened as well as shown; a file only its ancestors.
    const parts = revealTarget.split("/");
    const segments = reveal?.directory && reveal.path === revealTarget ? parts : parts.slice(0, -1);
    return new Set(segments.map((_, index) => segments.slice(0, index + 1).join("/")));
  }, [revealTarget, reveal]);

  const isExpanded = useCallback((directory) => expanded.has(directory), [expanded]);

  // The root, on every mount: the listings may survive a remount, but a tree
  // that trusted a cache taken before the last `git checkout` would show files
  // that are not there.
  useEffect(() => {
    load("");
  }, [load]);

  /**
   * The watcher fired: re-read every directory that is currently open.
   *
   * Keyed on the revision ALONE, with the open set read from a ref, because it
   * is a reaction to an event. As an effect over `expanded` it would re-read
   * the whole open tree every time a single folder was expanded.
   */
  const openDirectories = useMemo(
    () => Object.keys(children).filter((directory) => isExpanded(directory)),
    [children, isExpanded]
  );
  const openRef = useRef(openDirectories);
  useEffect(() => {
    openRef.current = openDirectories;
  }, [openDirectories]);

  const firstRevision = useRef(revision);
  useEffect(() => {
    if (revision === firstRevision.current) {
      return;
    }
    for (const directory of openRef.current) {
      load(directory);
    }
  }, [revision, load]);

  /**
   * The flat corpus behind the filter, fetched on the first keystroke and
   * again whenever the source has moved on since it was taken.
   *
   * Stamped with the revision it was read at rather than cleared by the
   * watcher: clearing is a synchronous setState in an effect, and the stamp
   * says the same thing without one.
   */
  const [corpus, setCorpus] = useState(null);
  const filtering = query.trim() !== "";
  const corpusStale = corpus === null || corpus.revision !== revision;

  useEffect(() => {
    if (!filtering || !corpusStale) {
      return;
    }
    let cancelled = false;
    void Promise.resolve(paths())
      .then((result) => {
        if (!cancelled) {
          setCorpus({ revision, paths: [...result] });
        }
      })
      .catch(() => {
        if (!cancelled) {
          setCorpus({ revision, paths: [] });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [filtering, corpusStale, revision, paths]);

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
          : new Set([...current, ...revealed])
      );
    }
    for (const directory of revealed) {
      load(directory);
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
    (directory) => {
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
        load(directory);
      }
    },
    [expanded, load, setExpanded]
  );

  /**
   * Begin a new entry in a folder: the folder is opened first, because a field
   * inside a shut folder is a field nobody can see.
   */
  const beginCreate = useCallback(
    (directory, kind) => {
      if (directory !== "" && !expanded.has(directory)) {
        setExpanded((current) => new Set([...current, directory]));
        load(directory);
      }
      setEditing({ mode: "create", directory, kind });
    },
    [expanded, load, setExpanded]
  );

  /**
   * The menu's one handler. The three items that start a field are the tree's
   * own business and never leave it; everything else is the host's.
   */
  const onMenuAction = useCallback(
    (action, entry) => {
      if (action === "rename") {
        setEditing({ mode: "rename", entry });
        return;
      }
      if (action === "new-file" || action === "new-folder") {
        beginCreate(entry.path, action === "new-file" ? "file" : "directory");
        return;
      }
      source.onAction(action, entry);
    },
    [beginCreate, source]
  );
  const menuGuard = useEntryMenuFocusGuard(onMenuAction);

  /**
   * A crumb asked for an edit. The folders above it are opened and read first
   * — a field in a folder the tree has shut is a field nobody sees — and the
   * request is honoured once per nonce.
   */
  const honoured = useRef(0);
  useEffect(() => {
    if (!edit || edit.nonce === honoured.current) {
      return;
    }
    honoured.current = edit.nonce;
    const target = edit.mode === "rename" ? edit.entry.path : edit.directory;
    const segments = target === "" ? [] : target.split("/");
    const ancestors = segments
      .slice(0, edit.mode === "rename" ? -1 : undefined)
      .map((_, index, all) => all.slice(0, index + 1).join("/"));
    if (ancestors.length > 0) {
      setExpanded((current) =>
        ancestors.every((directory) => current.has(directory))
          ? current
          : new Set([...current, ...ancestors])
      );
      for (const directory of ancestors) {
        load(directory);
      }
    }
    setQuery("");
    setEditing(
      edit.mode === "rename"
        ? { mode: "rename", entry: edit.entry }
        : { mode: "create", directory: edit.directory, kind: edit.kind }
    );
  }, [edit, setExpanded, load]);

  /**
   * When an inline field goes away the focus goes with it — to `body` — and
   * the next F2 or arrow key would be lost. The list takes it back, so a
   * rename from the keyboard ends where it began.
   */
  const wasEditing = useRef(false);
  useEffect(() => {
    if (wasEditing.current && editing === null) {
      listRef.current?.focus();
    }
    wasEditing.current = editing !== null;
  }, [editing]);

  /** The visible rows, flattened depth-first from what is expanded. */
  const rows = useMemo(() => {
    const out = [];
    const walk = (directory, depth) => {
      for (const entry of children[directory] ?? []) {
        const open = entry.kind === "directory" && isExpanded(entry.path);
        out.push({
          path: entry.path,
          name: entry.name,
          kind: entry.kind,
          depth,
          expanded: open
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
    [corpus, filtering, query]
  );

  const visible = filtering ? matches.map((match) => match.path) : rows.map((row) => row.path);

  // A cursor that has scrolled out of the list is worse than none: arrow keys
  // would move a selection nobody can see.
  const cursorPath = cursor && visible.includes(cursor) ? cursor : (visible[0] ?? null);

  const onKeyDown = (event) => {
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
    // The two edits the menu offers, from the keyboard: F2 and ⌘⌫
    // (Ctrl+Delete). Both only where the host offers the menu item too.
    if (row && event.key === "F2" && capabilities.has("rename")) {
      event.preventDefault();
      setEditing({ mode: "rename", entry: { path: row.path, kind: row.kind } });
      return;
    }
    if (
      row &&
      capabilities.has("trash") &&
      (event.key === "Backspace" || event.key === "Delete") &&
      (platform === "darwin" ? event.metaKey : event.ctrlKey) &&
      !event.altKey &&
      !event.shiftKey
    ) {
      event.preventDefault();
      void source.trash?.({ path: row.path, kind: row.kind });
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
   * Aim the menu. A row's `onContextMenu` runs before the list's — the trigger
   * — sees the same event, so the target is set by the time Radix opens the
   * menu; the empty space under the rows is the root.
   */
  const aim = (event) => {
    const row = event.target.closest?.("[data-path]");
    const path = row?.dataset.path ?? "";
    const kind = row?.dataset.kind === "file" ? "file" : "directory";
    setMenuTarget({ path, kind });
    if (row && path) {
      setCursor(path);
    }
  };

  const finishRename = async (entry, name) => {
    const renamed = (await source.rename?.(entry, name)) ?? null;
    if (renamed !== null) {
      setCursor(renamed);
      setEditing(null);
    }
    return renamed !== null;
  };

  const finishCreate = async (directory, kind, name) => {
    const created = (await source.create?.(directory, kind, name)) ?? null;
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
                {children[""] === undefined ? "Reading…" : `${rootName} is empty`}
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
                            cancel: () => setEditing(null)
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
        <ContextMenuContent
          className="w-56"
          data-entry-menu={menuTarget.path}
          onCloseAutoFocus={menuGuard.onCloseAutoFocus}
        >
          <EntryMenuItems
            capabilities={capabilities}
            entry={menuTarget}
            onAction={menuGuard.onAction}
            platform={platform}
          />
        </ContextMenuContent>
      </ContextMenu>
    </div>
  );
}

function TreeRow({ row, active, cursor, onSelect, onRename }) {
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
        cursor && !active && "bg-accent/30"
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

function FilterRow({ path, indices, active, cursor, onOpen }) {
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
        cursor && !active && "bg-accent/30"
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
function Highlight({ text, indices, from }) {
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
        )
      )}
    </>
  );
}
