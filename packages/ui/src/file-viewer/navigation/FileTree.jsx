import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { Fragment, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";

import { ContextMenu, ContextMenuContent, ContextMenuTrigger } from "@text-to-cad/ui/primitives/context-menu";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { TreeFilterHighlight, TreeFilterInput } from "@text-to-cad/ui/primitives/tree-filter";
import { TREE_ROW_HEIGHT, TreeRowSurface, TreeRowChevron, TreeRowLabel } from "@text-to-cad/ui/primitives/tree-row";

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
 * same two: F2 renames the focused row, ⌘⌫ (Ctrl+Delete) moves it to the trash
 * and says so. Both are capabilities, so in a browser tab neither key does
 * anything and neither item is in the menu.
 *
 * The rows are the focus, one Tab stop between them (a roving tabindex): the
 * arrows move focus row to row, and the row with focus is the cursor, the Tab
 * stop and the row every key acts on. The filter is a combobox over the ranked
 * list while it has a query: focus stays in the box, the arrows move the
 * cursor, and `aria-activedescendant` names it.
 *
 * ## The source adapter
 *
 * Where a listing comes from is the one thing the two hosts do not share, so
 * it is a prop rather than an import — the same shape `Breadcrumbs.jsx` takes,
 * for the same reason. The desktop reads a directory at a time over IPC with
 * gitignore semantics and a watcher behind it; the web host derives listings
 * from its catalog, so its tree shows the CAD files the catalog knows
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

const NO_FAILURES = Object.freeze({});
const FILTER_LIMIT = 200;
const ROW_HEIGHT = TREE_ROW_HEIGHT;
const INDENT = 12;

/**
 * Entries the tree leaves out: a repository's own internals, which are the
 * version control's and never something to open — the `.git` folder, or the
 * `.git` FILE at the root of a worktree. Other dotfiles and dotfolders
 * (`.gitignore`, `.github`, `.env`) are the project's and stay. A hidden
 * folder still shows while the open or revealed path is inside it.
 */
const HIDDEN_ENTRY_NAMES = new Set([".git"]);

/** True for an entry, file or folder, the tree leaves out. */
export function isHiddenTreeEntry(entry) {
  return HIDDEN_ENTRY_NAMES.has(entry.name);
}

/** True for a path that is, or is inside, an entry the tree leaves out: the filter does not rank it. */
export function isInsideHiddenTreeEntry(path) {
  return path.split("/").some((segment) => HIDDEN_ENTRY_NAMES.has(segment));
}

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
  /**
   * Bumped when a file picked from the filter is the one already open: the
   * reveal below keys on the open path, which did not move, so this asks for
   * it again.
   */
  const [revealAgain, setRevealAgain] = useState(0);
  /**
   * A file picked from the filter, scrolled to once the tree has its row —
   * and only while it is the file the tree reveals. A pick that did not open
   * (or a reveal aimed elsewhere) is dropped: the next pick replaces it, the
   * reveal moving to another path clears it, and so does a folder opened or
   * shut by hand, so it can never pull the tree somewhere later.
   */
  const pendingScroll = useRef(null);
  const [cursor, setCursor] = useState(null);
  /** @type {[TreeEditRequest|null, Function]} */
  const [editing, setEditing] = useState(null);
  /** The row the context menu is aimed at; the root when the empty space was clicked. */
  const [menuTarget, setMenuTarget] = useState({ path: "", kind: "directory" });
  const listRef = useRef(null);
  /** Said in the tree's own status region: the one edit that takes a row away without a field. */
  const [announcement, setAnnouncement] = useState("");
  const baseId = useId();
  const listId = `${baseId}-list`;
  const optionId = (index) => `${baseId}-option-${index}`;

  const {
    rootName,
    expanded,
    setExpanded,
    listings: children,
    failures = NO_FAILURES,
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
    // `revealAgain` is a request, not an input: a new set re-runs the reveal.
  }, [revealTarget, reveal, revealAgain]);

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
          const listing = Array.isArray(result) ? { paths: result, truncated: false } : result;
          setCorpus({ revision, paths: [...listing.paths], truncated: listing.truncated === true });
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setCorpus({ revision, paths: [], failure: error instanceof Error ? error.message : String(error) });
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
      pendingScroll.current = null;
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
      // The menu's Move to Trash and ⌘⌫ are one edit, announced the same way.
      if (action === "trash" && source.trash) {
        void trashEntryRef.current(entry);
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
   * the next F2 or arrow key would be lost. The row takes it back (the one
   * renamed or made, which is the cursor now), so a rename from the keyboard
   * ends where it began; the list, if that row is not drawn yet.
   */
  const wasEditing = useRef(false);
  useEffect(() => {
    if (wasEditing.current && editing === null) {
      const list = listRef.current;
      (list?.querySelector('[role=treeitem][tabindex="0"]') ?? list)?.focus();
    }
    wasEditing.current = editing !== null;
  }, [editing]);

  /** The visible rows, flattened depth-first from what is expanded. */
  const rows = useMemo(() => {
    const out = [];
    const walk = (directory, depth) => {
      for (const entry of children[directory] ?? []) {
        if (isHiddenTreeEntry(entry) && !revealed.has(entry.path) && entry.path !== revealTarget) {
          continue;
        }
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
  }, [children, isExpanded, revealed, revealTarget]);

  /**
   * The file picked from the filter, once its row is drawn: its folders open
   * a render or two after the pick (the reveal, then their listings).
   */
  useEffect(() => {
    const target = pendingScroll.current;
    if (!target || filtering || target !== revealTarget) {
      return;
    }
    const row = listRef.current?.querySelector(`[data-path="${CSS.escape(target)}"]`);
    if (row) {
      pendingScroll.current = null;
      row.scrollIntoView({ block: "nearest" });
    }
  }, [rows, filtering, revealTarget]);

  // The reveal moved on to another path: whatever was picked is not coming.
  const pickedRevealTarget = useRef(revealTarget);
  useEffect(() => {
    if (revealTarget !== pickedRevealTarget.current) {
      pickedRevealTarget.current = revealTarget;
      if (pendingScroll.current !== revealTarget) {
        pendingScroll.current = null;
      }
    }
  }, [revealTarget]);

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

  const ranked = useMemo(
    () => (filtering ? fuzzyFilter((corpus?.paths ?? []).filter((path) => !isInsideHiddenTreeEntry(path)), query, Infinity) : []),
    [corpus, filtering, query]
  );
  const matches = useMemo(() => ranked.slice(0, FILTER_LIMIT), [ranked]);
  /** What the filter could not show: matches past the cap, and files the source's index never held. */
  const filterNotice = (() => {
    if (!filtering || !corpus || corpus.failure !== undefined) return null;
    const over = ranked.length > FILTER_LIMIT ? `Showing the first ${FILTER_LIMIT} of ${ranked.length} matches` : null;
    const capped = corpus.truncated ? `the index stopped at ${corpus.paths.length.toLocaleString("en-US")} files` : null;
    if (over && capped) return `${over}; ${capped}`;
    return over ?? (capped ? `${capped[0].toUpperCase()}${capped.slice(1)}; some matches may be missing` : null);
  })();

  /**
   * Open a file. One picked from the filter ends the search: the tree comes
   * back, revealed to the file, rather than a one-row list that makes its
   * folder look as if the file were all there is in it.
   */
  const open = (path) => {
    if (filtering) {
      setQuery("");
      setCursor(path);
      pendingScroll.current = path;
      if (path === activePath) {
        setRevealAgain((count) => count + 1);
      }
    }
    onOpen(path);
  };

  const visible = filtering ? matches.map((match) => match.path) : rows.map((row) => row.path);

  // The keyboard cursor goes where the open file goes, however it was opened —
  // from this tree, a tab or a link in the transcript. Left where it was, it
  // sat on the row picked last (or the first row) as a second highlight beside
  // the file actually open.
  const [cursorFollows, setCursorFollows] = useState(activePath);
  if (activePath !== cursorFollows) {
    setCursorFollows(activePath);
    if (activePath) setCursor(activePath);
  }
  // A cursor that has scrolled out of the list is worse than none: arrow keys
  // would move a selection nobody can see. With none put anywhere the keys
  // start from the open file, else the first row — but that fallback is not
  // drawn: a row tinted before anyone moved to it reads as a second selection.
  // Filtering is the exception, where it is the match Enter opens.
  const placed = cursor && visible.includes(cursor) ? cursor : null;
  const cursorPath = placed ?? (activePath && visible.includes(activePath) ? activePath : (visible[0] ?? null));
  const drawnCursor = filtering ? cursorPath : placed;
  // Where Tab lands in the tree: the cursor row, else the open file, else the
  // first row. The keys act on the row with focus, never on an undrawn cursor —
  // ⌘⌫ on the list itself once trashed a folder nobody had picked — and a row
  // with focus is the cursor, drawn.
  const stopPath = filtering ? null : cursorPath;

  /** Put the keyboard on a row: the cursor, and so the Tab stop, follows it. */
  const focusRow = (path) => {
    if (!path) return;
    setCursor(path);
    listRef.current?.querySelector(`[role=treeitem][data-path="${CSS.escape(path)}"]`)?.focus();
  };

  /**
   * Move an entry to the trash and say so. The row goes with it, and focus on
   * it would go to the page: it moves to the row after, or before, first.
   */
  const trashEntry = async (entry) => {
    const at = rows.findIndex((row) => row.path === entry.path);
    const inside = (path) => path === entry.path || path.startsWith(`${entry.path}/`);
    const neighbour = rows.slice(at + 1).find((row) => !inside(row.path)) ?? rows.slice(0, Math.max(at, 0)).reverse()[0];
    const hadFocus = Boolean(listRef.current?.contains(document.activeElement));
    const moved = await source.trash?.(entry);
    if (!moved) return;
    setAnnouncement(`Moved ${entry.path.split("/").pop()} to the Trash`);
    if (neighbour && (hadFocus || document.activeElement === document.body)) focusRow(neighbour.path);
  };
  // Read by the menu's handler, which is memoised on the source alone.
  const trashEntryRef = useRef(trashEntry);
  useEffect(() => {
    trashEntryRef.current = trashEntry;
  });

  /** A focused row's keys. Only a row's own: an inline name's field keeps its keys. */
  const onTreeKeyDown = (event) => {
    const element = event.target;
    if (!(element instanceof HTMLElement) || element.getAttribute("role") !== "treeitem") return;
    const at = rows.findIndex((candidate) => candidate.path === element.dataset.path);
    const row = rows[at];
    if (!row) return;
    const move = (path) => {
      event.preventDefault();
      focusRow(path);
    };
    if (event.key === "ArrowDown") return move(rows[Math.min(at + 1, rows.length - 1)]?.path);
    if (event.key === "ArrowUp") return move(rows[Math.max(at - 1, 0)]?.path);
    if (event.key === "Home") return move(rows[0]?.path);
    if (event.key === "End") return move(rows[rows.length - 1]?.path);
    // The two edits the menu offers, from the keyboard: F2 and ⌘⌫
    // (Ctrl+Delete). Both only where the host offers the menu item too.
    if (event.key === "F2" && capabilities.has("rename")) {
      event.preventDefault();
      setEditing({ mode: "rename", entry: { path: row.path, kind: row.kind } });
      return;
    }
    if (
      capabilities.has("trash") &&
      (event.key === "Backspace" || event.key === "Delete") &&
      (platform === "darwin" ? event.metaKey : event.ctrlKey) &&
      !event.altKey &&
      !event.shiftKey
    ) {
      event.preventDefault();
      void trashEntry({ path: row.path, kind: row.kind });
      return;
    }
    if (event.key === "ArrowRight" && row.kind === "directory") {
      event.preventDefault();
      // Open, then into it.
      if (!row.expanded) toggle(row.path);
      else if (rows[at + 1]?.depth > row.depth) focusRow(rows[at + 1].path);
      return;
    }
    if (event.key === "ArrowLeft") {
      event.preventDefault();
      // Shut, then up to the folder it is in.
      if (row.kind === "directory" && row.expanded) toggle(row.path);
      else focusRow(rows.slice(0, at).reverse().find((candidate) => candidate.depth < row.depth)?.path);
      return;
    }
    if (event.key === "Enter") {
      // Not the button's own click as well.
      event.preventDefault();
      if (row.kind === "directory") {
        toggle(row.path);
      } else {
        onOpen(row.path);
      }
    }
  };

  /**
   * The filter's keys. With a query, the combobox's: the arrows move the
   * cursor through the ranked list and Enter opens it. Without one, ArrowDown
   * goes into the tree. F2 and ⌘⌫ are the box's own here (⌘⌫ deletes the text
   * before the caret), never an edit of a row the person is not on.
   */
  const onFilterKeyDown = (event) => {
    if (!filtering) {
      if (event.key === "ArrowDown" && stopPath) {
        event.preventDefault();
        focusRow(stopPath);
      }
      return;
    }
    if (visible.length === 0 || !cursorPath) return;
    const at = visible.indexOf(cursorPath);
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setCursor(visible[Math.min(at + 1, visible.length - 1)] ?? null);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setCursor(visible[Math.max(at - 1, 0)] ?? null);
    } else if (event.key === "Enter") {
      event.preventDefault();
      open(cursorPath);
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
      // A row of the tree, as the tree's children must be; its field is what has focus.
      <div
        aria-label={editing.kind === "directory" ? "New folder" : "New file"}
        className="flex w-full items-center gap-1.5 pr-2"
        key="__new__"
        role="treeitem"
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
      <TreeFilterInput data-mobile-panel-top-row=""
        inputProps={{
          role: "combobox",
          "aria-autocomplete": "list",
          "aria-controls": listId,
          "aria-expanded": filtering,
          "aria-activedescendant": filtering && cursorPath ? optionId(visible.indexOf(cursorPath)) : undefined
        }}
        label="Filter files"
        onChange={setQuery}
        onKeyDown={onFilterKeyDown}
        placeholder="Filter files…"
        value={query}
      />
      <div aria-live="polite" className="sr-only" role="status">{announcement}</div>

      <ContextMenu modal={false}>
        <ContextMenuTrigger asChild>
          <ScrollArea
            className="min-h-0 flex-1"
            onContextMenu={aim}
            viewportClassName="px-1 py-1"
            // A tree of rows (busy while the root is read), or the filter's ranked list — not
            // while it has no match, when its line is not an option. Not a Tab stop: a row is.
            viewportProps={{
              id: listId,
              onKeyDown: filtering ? undefined : onTreeKeyDown,
              role: filtering ? (matches.length > 0 ? "listbox" : undefined) : "tree",
              "aria-busy": !filtering && children[""] === undefined && failures[""] === undefined ? true : undefined,
              "aria-label": filtering ? "Matching files" : "Files",
              tabIndex: -1
            }}
            viewportRef={listRef}
          >
            {filtering ? (
              matches.length === 0 ? (
                <p className="px-3 py-6 text-center text-xs text-muted-foreground">
                  {corpus === null ? "Searching…" : corpus.failure !== undefined ? `Could not search the files: ${corpus.failure}` : `No file matches “${query.trim()}”${corpus.truncated ? `; the index stopped at ${corpus.paths.length.toLocaleString("en-US")} files` : ""}`}
                </p>
              ) : (
                <>
                {matches.map((match, index) => (
                  <FilterRow
                    active={match.path === activePath || match.path === reveal?.path}
                    cursor={match.path === drawnCursor}
                    id={optionId(index)}
                    indices={match.indices}
                    key={match.path}
                    onOpen={() => open(match.path)}
                    path={match.path}
                  />
                ))}
                {filterNotice ? <p className="px-3 py-2 text-xs text-muted-foreground" role="presentation">{filterNotice}</p> : null}
                </>
              )
            ) : rows.length === 0 && !newEntryRow ? (
              <p className="px-3 py-6 text-center text-xs text-muted-foreground">
                {children[""] === undefined && failures[""] !== undefined ? (
                  <ListingError message={failures[""]} onRetry={() => load("")} />
                ) : children[""] === undefined ? "Reading…" : `${rootName} is empty`}
              </p>
            ) : (
              <>
                {creatingAt === 0 ? newEntryRow : null}
                {rows.map((row, index) => (
                  <Fragment key={row.path}>
                    <TreeRow
                      active={row.path === activePath || row.path === reveal?.path}
                      cursor={row.path === drawnCursor}
                      onFocus={() => {
                        if (cursor !== row.path) setCursor(row.path);
                      }}
                      stop={row.path === stopPath}
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
                    {row.kind === "directory" && row.expanded && children[row.path] === undefined && failures[row.path] !== undefined ? (
                      <ListingError depth={row.depth + 1} message={failures[row.path]} onRetry={() => load(row.path)} />
                    ) : null}
                    {creatingAt === index + 1 ? newEntryRow : null}
                  </Fragment>
                ))}
              </>
            )}
          </ScrollArea>
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

/** A directory that could not be read: the sentence, where its rows would be, and a way to ask again. */
function ListingError({ message, onRetry, depth = null }) {
  return (
    <span className="flex flex-wrap items-center gap-x-2 text-xs text-muted-foreground" data-listing-error role="alert"
      style={depth === null ? undefined : { paddingLeft: 6 + depth * INDENT + 20, minHeight: ROW_HEIGHT }}>
      <span>{message}</span>
      <button className="rounded-sm underline outline-none focus-visible:ring-2 focus-visible:ring-ring" onClick={onRetry} type="button">Retry</button>
    </span>
  );
}

function TreeRow({ row, active, cursor, stop, onFocus, onSelect, onRename }) {
  const icon =
    row.kind === "directory" ? (
      <FolderIcon className="size-3.5 shrink-0 text-muted-foreground" open={row.expanded} />
    ) : (
      <FileIcon className="size-3.5 shrink-0 text-muted-foreground" path={row.path} />
    );
  const chevron = <TreeRowChevron expanded={row.expanded} branch={row.kind === "directory"} />;

  if (onRename) {
    return (
      <div
        aria-label={row.name}
        className="flex w-full items-center gap-1.5 pr-2"
        data-kind={row.kind}
        data-path={row.path}
        role="treeitem"
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
    <TooltipHint content={row.path} overflowOnly><TreeRowSurface
      as="button"
      active={active}
      cursor={cursor}
      aria-expanded={row.kind === "directory" ? row.expanded : undefined}
      aria-level={row.depth + 1}
      aria-selected={active}
      className="outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ring/45"
      data-kind={row.kind}
      data-path={row.path}
      onClick={onSelect}
      onFocus={onFocus}
      role="treeitem"
      style={{ height: ROW_HEIGHT, paddingLeft: 6 + row.depth * INDENT }}
      tabIndex={stop ? 0 : -1}

      type="button"
    >
      {chevron}
      {icon}
      <TreeRowLabel>{row.name}</TreeRowLabel>
    </TreeRowSurface></TooltipHint>
  );
}

function FilterRow({ id, path, indices, active, cursor, onOpen }) {
  const lastSlash = path.lastIndexOf("/");
  const directory = lastSlash < 0 ? "" : path.slice(0, lastSlash + 1);
  return (
    <TooltipHint content={path} overflowOnly><TreeRowSurface
      as="button"
      active={active}
      cursor={cursor}
      // The option the filter's Enter opens: the one `aria-activedescendant` names.
      aria-selected={cursor}
      className="px-2"
      data-kind="file"
      data-path={path}
      id={id}
      onClick={onOpen}
      role="option"
      // The filter keeps focus while the list is up; a pointer picks.
      tabIndex={-1}
      style={{ height: ROW_HEIGHT }}

      type="button"
    >
      <FileIcon className="size-3.5 shrink-0 text-muted-foreground" path={path} />
      <TreeRowLabel>
        {directory ? <span className="text-muted-foreground">{directory}</span> : null}
        <TreeFilterHighlight from={directory.length} indices={indices} text={path.slice(directory.length)} />
      </TreeRowLabel>
    </TreeRowSurface></TooltipHint>
  );
}
