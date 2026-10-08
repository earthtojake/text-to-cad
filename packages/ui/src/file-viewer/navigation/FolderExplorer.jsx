import { ChevronRight, Ellipsis, LoaderCircle } from "lucide-react";
import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@text-to-cad/ui/primitives/dropdown-menu";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { TreeFilterInput } from "@text-to-cad/ui/primitives/tree-filter";
import { TREE_GLYPH_CLASS, TREE_GLYPH_STROKE, TREE_INDENT_PX, TreeRowChevron, TreeRowGuides, TreeRowLabel, TreeRowSurface } from "@text-to-cad/ui/primitives/tree-row";
import { cn } from "@text-to-cad/ui/utils";
import { FileIcon, FolderIcon } from "./icons.jsx";

// The wait after a keystroke before the filter searches; each keystroke cancels the search before it.
const SEARCH_DELAY_MS = 150;
// The most of the path's last folders the breadcrumb shows; the ones above them are the ellipsis's.
const SHOWN_FOLDERS = 3;
// A crumb is a folder's whole name, never cut: the ones that do not fit go into the ellipsis. Only
// the folder the explorer is in, left on its own, is cut to the row.
const CRUMB_CLASS = "rounded-sm px-1 py-0.5 hover:bg-accent/50 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45";
const CRUMB = `${CRUMB_CLASS} shrink-0 whitespace-nowrap text-muted-foreground`;
const CURRENT_CRUMB = `${CRUMB_CLASS} min-w-0 truncate text-foreground`;
// A row is the trees' compact line (`TreeRowSurface`) in 12px text. Its kind is the trees' small,
// light glyph -- a folder its disclosure chevron, a file its type's icon -- in one column, so the
// names carry the list; a folder opened inline holds its rows a level further in, hung from the
// trees' faint lines (`TreeRowGuides`).
const ROW_INSET_PX = 8;
const rowInset = depth => ROW_INSET_PX + depth * TREE_INDENT_PX;

/** The folders from the top of `path`'s filesystem down to it, as `{ name, path }` with `/` separators. */
export function folderTrail(path) {
  const normal = String(path).replace(/\\/g, "/");
  const drive = /^[A-Za-z]:/.test(normal) ? normal.slice(0, 2) : "";
  const trail = [{ name: drive || "/", path: `${drive}/` }];
  let current = drive;
  for (const part of normal.slice(drive.length).split("/").filter(Boolean)) {
    current = `${current}/${part}`;
    trail.push({ name: part, path: current });
  }
  return trail;
}

/** The folder holding `path`: the top of its filesystem holds itself. */
export function parentFolder(path) {
  const trail = folderTrail(path);
  return trail[Math.max(0, trail.length - 2)].path;
}

/**
 * How many of the path's last folders the breadcrumb shows (up to `SHOWN_FOLDERS`, the folder it is
 * in always): one fewer each time that folder is cut, the farthest going first into the ellipsis, all
 * measured before the row is painted, and again when the folder or the row's width changes.
 */
function useCrumbsThatFit(rowRef, currentRef, folder, folders) {
  const [width, setWidth] = useState(0);
  useLayoutEffect(() => {
    const row = rowRef.current;
    if (!row) return undefined;
    const measure = () => setWidth(Math.round(row.clientWidth));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(row);
    return () => observer.disconnect();
  }, [rowRef]);
  const key = `${folder}\u0000${width}`;
  const [fit, setFit] = useState({ key: "", shown: SHOWN_FOLDERS });
  const shown = Math.min(folders, fit.key === key ? fit.shown : SHOWN_FOLDERS);
  useLayoutEffect(() => {
    const current = currentRef.current;
    if (shown > 1 && current && current.scrollWidth > current.clientWidth) setFit({ key, shown: shown - 1 });
  });
  return shown;
}

function Note({ children, busy = false }) {
  return <p className="px-3 py-4 text-center text-xs text-muted-foreground" role={busy ? "status" : undefined}>
    {busy ? <LoaderCircle className="mr-1.5 inline size-3 animate-spin align-[-2px]" aria-hidden="true" /> : null}{children}
  </p>;
}

/** What a folder opened inline says while it has no rows to show: a row's height, in its glyph's column. */
function InlineNote({ depth, busy = false, children }) {
  return <p className="relative flex h-6 items-center gap-1.5 text-xs text-muted-foreground" style={{ paddingLeft: rowInset(depth) }}
    role={busy ? "status" : undefined}>
    <TreeRowGuides depth={depth} inset={ROW_INSET_PX} />
    <span className="flex size-3 shrink-0 items-center">{busy ? <LoaderCircle className="size-3 animate-spin" aria-hidden="true" /> : null}</span>
    {children}
  </p>;
}

function Row({ kind, path, detail = "", name, depth = 0, active = false, expanded = false, onClick, onDoubleClick }) {
  return <TooltipHint content={path} overflowOnly><TreeRowSurface as="button" type="button" active={active}
    style={{ paddingLeft: rowInset(depth) }}
    data-explorer-row="" data-kind={kind} data-path={path} aria-current={active ? "true" : undefined}
    aria-expanded={kind === "directory" ? expanded : undefined} onClick={onClick} onDoubleClick={onDoubleClick}>
    <TreeRowGuides depth={depth} inset={ROW_INSET_PX} />
    {kind === "directory" ? <TreeRowChevron expanded={expanded} />
      : <FileIcon className={TREE_GLYPH_CLASS} path={path} strokeWidth={TREE_GLYPH_STROKE} />}
    <TreeRowLabel>{detail ? <span className="text-muted-foreground">{detail}</span> : null}{name}</TreeRowLabel>
  </TreeRowSurface></TooltipHint>;
}

/**
 * The file explorer: what the navbar's file name opens. It starts in the open file's folder and
 * lists one folder at a time -- its subfolders, then its CAD files -- read from `source` as it is
 * reached, so nothing walks a tree to show it. A press on a subfolder opens it inline, under itself
 * and a little further in (read once, when first opened); a double-click opens it in the
 * explorer's place, as a crumb does. The breadcrumb climbs: as many of the path's last three
 * folders as fit whole -- the folder it is in always, cut only once it is alone -- and an ellipsis
 * whose menu holds the ones above them. "Filter files..." searches every CAD file nested under the
 * folder it is in (`source.search`, bounded by the server, which says when it stopped early). A
 * pick is `onOpen`; whoever holds the explorer puts it away.
 *
 * @param {{ source: Pick<import("../types").FileSource, "list" | "search">, file: string, onOpen(path: string): void }} props
 */
export function FolderExplorer({ source, file, onOpen }) {
  const [folder, setFolder] = useState(() => parentFolder(file));
  const [listing, setListing] = useState({ folder: "", entries: null, error: null });
  const [query, setQuery] = useState("");
  const [found, setFound] = useState(null);
  // The folders opened inline, by path, and what each holds once it has been read.
  const [open, setOpen] = useState(() => new Set());
  const [held, setHeld] = useState(() => new Map());
  const reads = useRef(new Map());
  const rows = useRef(null);
  const crumbRow = useRef(null);
  const currentCrumb = useRef(null);
  const term = query.trim();

  useEffect(() => {
    const controller = new AbortController();
    source.list(folder, { signal: controller.signal }).then(
      // A source that answers anyway once cancelled must not land over the folder now shown.
      entries => { if (!controller.signal.aborted) setListing({ folder, entries, error: null }); },
      error => { if (!controller.signal.aborted) setListing({ folder, entries: null, error }); },
    );
    return () => controller.abort();
  }, [source, folder]);
  useEffect(() => {
    if (!term) return undefined;
    const controller = new AbortController();
    const timer = setTimeout(() => source.search(folder, term, { signal: controller.signal }).then(
      result => { if (!controller.signal.aborted) setFound({ folder, term, ...result }); },
      error => { if (!controller.signal.aborted) setFound({ folder, term, error }); },
    ), SEARCH_DELAY_MS);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [source, folder, term]);
  // A folder opened inline is read once; a read that failed is tried again the next time it opens.
  useEffect(() => () => { for (const controller of reads.current.values()) controller.abort(); }, []);
  const read = useCallback(path => {
    if (reads.current.has(path)) return;
    const controller = new AbortController();
    reads.current.set(path, controller);
    source.list(path, { signal: controller.signal }).then(entries => ({ entries, error: null }), error => ({ entries: null, error }))
      .then(content => {
        if (controller.signal.aborted) return;
        if (content.error) reads.current.delete(path);
        setHeld(current => new Map(current).set(path, content));
      });
  }, [source]);
  const toggle = path => {
    const opening = !open.has(path);
    setOpen(current => { const next = new Set(current); if (opening) next.add(path); else next.delete(path); return next; });
    if (opening) read(path);
  };

  // A folder opened in the explorer's place is not left open inline for when the explorer climbs back.
  const go = path => {
    setFolder(path);
    setQuery("");
    setOpen(current => { if (!current.has(path)) return current; const next = new Set(current); next.delete(path); return next; });
  };
  // Arrows walk the rows on screen, from the filter into the list and back; on a folder, Right opens
  // it inline and Left closes it.
  const walk = (event, from) => {
    if (from?.dataset.kind === "directory" && (event.key === "ArrowRight" || event.key === "ArrowLeft")) {
      event.preventDefault();
      if ((event.key === "ArrowRight") !== open.has(from.dataset.path)) toggle(from.dataset.path);
      return;
    }
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const all = [...(rows.current?.querySelectorAll("[data-explorer-row]") ?? [])];
    const at = from ? all.indexOf(from) : -1;
    const next = event.key === "ArrowDown" ? all[at + 1] : at > 0 ? all[at - 1] : null;
    event.preventDefault();
    if (next) next.focus();
    else if (event.key === "ArrowUp") event.currentTarget.closest("[data-folder-explorer]")?.querySelector("input")?.focus();
  };

  // A folder's rows, `depth` folders in: its subfolders, each with what it holds under it while it is
  // open inline, then its files.
  const rowsOf = (entries, depth) => entries.map(entry => {
    if (entry.kind !== "directory") return <Row key={entry.path} kind="file" path={entry.path} name={entry.name} depth={depth}
      active={entry.path === file} onClick={() => onOpen(entry.path)} />;
    const expanded = open.has(entry.path);
    return <Fragment key={entry.path}>
      {/* The second press of a double-click is the double-click's: the folder opens in the explorer's place. */}
      <Row kind="directory" path={entry.path} name={entry.name} depth={depth} expanded={expanded}
        onClick={event => { if (event.detail < 2) toggle(entry.path); }} onDoubleClick={() => go(entry.path)} />
      {expanded ? <div role="group" aria-label={entry.name}>{inside(entry.path, depth + 1)}</div> : null}
    </Fragment>;
  });
  const inside = (path, depth) => {
    const content = held.get(path);
    if (!content) return <InlineNote depth={depth} busy>Loading…</InlineNote>;
    if (content.error) return <InlineNote depth={depth}>Couldn't read this folder</InlineNote>;
    if (!content.entries.length) return <InlineNote depth={depth}>No CAD files</InlineNote>;
    return rowsOf(content.entries, depth);
  };

  const trail = folderTrail(folder);
  const shownFolders = useCrumbsThatFit(crumbRow, currentCrumb, folder, trail.length);
  const above = trail.slice(0, trail.length - shownFolders);
  const prefix = folder.endsWith("/") ? folder : `${folder}/`;
  const current = listing.folder === folder ? listing : { entries: null, error: null };
  const result = term && found?.folder === folder && found.term === term ? found : null;
  let body;
  if (term) {
    if (!result) body = <Note busy>Searching…</Note>;
    else if (result.error) body = <Note>Couldn't search this folder</Note>;
    else if (!result.paths.length) body = <Note>{result.truncated ? "No files match yet. Keep typing to narrow the search." : "No files match"}</Note>;
    else body = <>
      {result.paths.map(path => {
        const relative = path.startsWith(prefix) ? path.slice(prefix.length) : path;
        const slash = relative.lastIndexOf("/");
        return <Row key={path} kind="file" path={path} active={path === file} detail={slash < 0 ? "" : relative.slice(0, slash + 1)}
          name={relative.slice(slash + 1)} onClick={() => onOpen(path)} />;
      })}
      {result.truncated ? <Note>Stopped early. Keep typing to narrow the search.</Note> : null}
    </>;
  } else if (current.error) body = <Note>Couldn't read this folder</Note>;
  else if (!current.entries) body = <Note busy>Loading…</Note>;
  else if (!current.entries.length) body = <Note>No CAD files here</Note>;
  else body = rowsOf(current.entries, 0);

  return <div className="flex min-h-0 flex-1 flex-col" data-folder-explorer="">
    <nav aria-label="Folders" ref={crumbRow} className="flex min-w-0 shrink-0 items-center gap-0.5 px-2 pt-2 pb-1 text-xs">
      {above.length ? <>
        <DropdownMenu modal={false}>
          <DropdownMenuTrigger asChild><button type="button" className={cn(CRUMB, "flex items-center")} aria-label="Folders above">
            <Ellipsis className="size-3.5" aria-hidden="true" />
          </button></DropdownMenuTrigger>
          <DropdownMenuContent align="start" className="min-w-40">
            {above.map(item => <DropdownMenuItem key={item.path} onSelect={() => go(item.path)}>
              <FolderIcon className="size-3.5 shrink-0 text-muted-foreground" open={false} />{item.name}
            </DropdownMenuItem>)}
          </DropdownMenuContent>
        </DropdownMenu>
        <ChevronRight className="size-3 shrink-0 text-muted-foreground" aria-hidden="true" />
      </> : null}
      {trail.slice(above.length).map((item, index) => <Fragment key={item.path}>
        {index ? <ChevronRight className="size-3 shrink-0 text-muted-foreground" aria-hidden="true" /> : null}
        {item.path === folder
          ? <TooltipHint content={item.name} overflowOnly><button type="button" ref={currentCrumb} className={CURRENT_CRUMB}
            aria-current="location" onClick={() => go(item.path)}>{item.name}</button></TooltipHint>
          : <button type="button" className={CRUMB} onClick={() => go(item.path)}>{item.name}</button>}
      </Fragment>)}
    </nav>
    <TreeFilterInput label="Filter files" placeholder="Filter files..." value={query} onChange={setQuery} onKeyDown={event => walk(event, null)} />
    <ScrollArea className="min-h-0 flex-1" viewportClassName="p-1" viewportRef={rows}
      viewportProps={{ onKeyDown: event => walk(event, event.target.closest?.("[data-explorer-row]") ?? null) }}>
      {body}
    </ScrollArea>
  </div>;
}
