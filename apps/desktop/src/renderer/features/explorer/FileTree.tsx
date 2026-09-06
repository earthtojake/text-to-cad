import { ChevronDown, ChevronRight, PanelRightClose, Search, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@renderer/components/ui/button";
import { cn } from "@renderer/lib/utils";
import { useExplorer } from "@renderer/state/explorer";
import type { DirEntry } from "@shared/ipc/explorer";

import { FileIcon, FolderIcon } from "./icons";
import { fuzzyFilter } from "./fuzzy";

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

export function FileTree({
  projectId,
  projectName,
  activePath,
  reveal = null,
  onOpen,
  onCollapse,
  fsRevision,
}: {
  projectId: string;
  projectName: string;
  /** The file the tab is showing, highlighted in the tree. */
  activePath: string | null;
  /**
   * A path to expand to and select without opening it — an agent's `reveal`
   * (src/renderer/state/explorer.ts). Wins over `activePath` for the reveal
   * and the scroll; the open file stays highlighted too.
   */
  reveal?: { path: string; directory: boolean } | null;
  onOpen: (path: string) => void;
  onCollapse: () => void;
  /** Bumped by `files.changed`; re-reads whatever is currently expanded. */
  fsRevision: number;
}) {
  const [children, setChildren] = useState<Record<string, DirEntry[]>>({});
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState<string | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);

  /**
   * Which folders are open, as *overrides* on a default rather than as the
   * whole answer.
   *
   * The default is "the ancestors of the open file are open", which is what
   * reveals `apps › desktop › build` when `icon.png` opens. Storing that by
   * writing it into the open set would be a setState in an effect — a render
   * cascade on every file opened — and it would fight the person: a folder
   * they shut by hand would spring back. An override map says both things at
   * once, and the reveal costs nothing.
   */
  const [override, setOverride] = useState<Record<string, boolean>>({ "": true });

  const revealTarget = reveal?.path ?? activePath;
  const revealed = useMemo(() => {
    if (!revealTarget) {
      return new Set<string>();
    }
    // A revealed folder is opened as well as shown; a file only its ancestors.
    const parts = revealTarget.split("/");
    const segments = reveal?.directory && reveal.path === revealTarget ? parts : parts.slice(0, -1);
    return new Set(segments.map((_, index) => segments.slice(0, index + 1).join("/")));
  }, [revealTarget, reveal]);

  const isExpanded = useCallback(
    (directory: string) => override[directory] ?? revealed.has(directory),
    [override, revealed],
  );

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
        .list({ projectId, path: directory })
        .then((entries: DirEntry[]) =>
          setChildren((current) => ({ ...current, [directory]: entries })),
        )
        .catch(() => {}),
    [projectId],
  );

  // The root. The component is keyed on `projectId` by its parent, so there is
  // no old project's tree to clear first — a remount is the reset.
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
        if (state.fsRevision !== previous.fsRevision) {
          for (const directory of openRef.current) {
            void load(directory);
          }
        }
      }),
    [load],
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
      .paths({ projectId, path: "" })
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
  }, [filtering, corpusStale, fsRevision, projectId]);

  // The revealed ancestors are open by default, but their children still have
  // to be read before there is anything to show.
  useEffect(() => {
    for (const directory of revealed) {
      void load(directory);
    }
  }, [revealed, load]);

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

  const toggle = useCallback(
    (directory: string) => {
      const opening = !isExpanded(directory);
      setOverride((current) => ({ ...current, [directory]: opening }));
      if (opening) {
        void load(directory);
      }
    },
    [isExpanded, load],
  );

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
        <Button
          aria-label="Hide file tree"
          className="size-6 shrink-0 text-muted-foreground"
          onClick={onCollapse}
          size="icon-xs"
          variant="ghost"
        >
          <PanelRightClose className="size-3.5" />
        </Button>
      </div>

      <div
        className="min-h-0 flex-1 overflow-auto py-1 outline-none"
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
        ) : rows.length === 0 ? (
          <p className="px-3 py-6 text-center text-xs text-muted-foreground">
            {children[""] === undefined ? "Reading…" : `${projectName} is empty`}
          </p>
        ) : (
          rows.map((row) => (
            <TreeRow
              active={row.path === activePath || row.path === reveal?.path}
              cursor={row.path === cursorPath}
              key={row.path}
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
          ))
        )}
      </div>
    </div>
  );
}

function TreeRow({
  row,
  active,
  cursor,
  onSelect,
}: {
  row: Row;
  active: boolean;
  cursor: boolean;
  onSelect: () => void;
}) {

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
      data-path={row.path}
      onClick={onSelect}
      role="treeitem"
      style={{ height: ROW_HEIGHT, paddingLeft: 6 + row.depth * INDENT }}
      title={row.path}
      type="button"
    >
      {row.kind === "directory" ? (
        row.expanded ? (
          <ChevronDown className="size-3 shrink-0 text-muted-foreground" />
        ) : (
          <ChevronRight className="size-3 shrink-0 text-muted-foreground" />
        )
      ) : (
        <span className="w-3 shrink-0" />
      )}
      {row.kind === "directory" ? (
        <FolderIcon className="size-3.5 shrink-0 text-muted-foreground" open={row.expanded} />
      ) : (
        <FileIcon className="size-3.5 shrink-0 text-muted-foreground" path={row.path} />
      )}
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
