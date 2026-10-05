import { ChevronRight, LoaderCircle } from "lucide-react";
import { Fragment, useEffect, useRef, useState } from "react";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@text-to-cad/ui/primitives/dropdown-menu";
import { ScrollArea } from "@text-to-cad/ui/primitives/scroll-area";
import { TooltipHint } from "@text-to-cad/ui/primitives/tooltip";
import { TreeFilterInput } from "@text-to-cad/ui/primitives/tree-filter";
import { TreeRowLabel, TreeRowSurface } from "@text-to-cad/ui/primitives/tree-row";
import { cn } from "@text-to-cad/ui/utils";
import { FileIcon, FolderIcon } from "./icons.jsx";

// The wait after a keystroke before the filter searches; each keystroke cancels the search before it.
const SEARCH_DELAY_MS = 150;
// The breadcrumb's last folders; the ones above them are the ellipsis's.
const SHOWN_FOLDERS = 3;
const CRUMB = "min-w-0 shrink truncate rounded-sm px-1 py-0.5 text-muted-foreground hover:bg-accent/50 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45";

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

function Note({ children, busy = false }) {
  return <p className="px-3 py-4 text-center text-xs text-muted-foreground" role={busy ? "status" : undefined}>
    {busy ? <LoaderCircle className="mr-1.5 inline size-3 animate-spin align-[-2px]" aria-hidden="true" /> : null}{children}
  </p>;
}

function Row({ kind, path, detail = "", name, active, onClick }) {
  return <TooltipHint content={path} overflowOnly><TreeRowSurface as="button" type="button" active={active} className="px-2"
    data-explorer-row="" data-kind={kind} data-path={path} aria-current={active ? "true" : undefined} onClick={onClick}>
    {kind === "directory" ? <FolderIcon className="size-3.5 shrink-0 text-muted-foreground" open={false} />
      : <FileIcon className="size-3.5 shrink-0 text-muted-foreground" path={path} />}
    <TreeRowLabel>{detail ? <span className="text-muted-foreground">{detail}</span> : null}{name}</TreeRowLabel>
  </TreeRowSurface></TooltipHint>;
}

/**
 * The file explorer: what the navbar's file name opens. It starts in the open file's folder and
 * lists one folder at a time -- its subfolders, then its CAD files -- read from `source` as it is
 * reached, so nothing walks a tree to show it. The breadcrumb climbs: the last three folders of the
 * path, and an ellipsis whose menu holds the ones above them. "Filter files..." searches every CAD
 * file nested under the folder it is in (`source.search`, bounded by the server, which says when it
 * stopped early). A pick is `onOpen`; whoever holds the explorer puts it away.
 *
 * @param {{ source: Pick<import("../types").FileSource, "list" | "search">, file: string, onOpen(path: string): void }} props
 */
export function FolderExplorer({ source, file, onOpen }) {
  const [folder, setFolder] = useState(() => parentFolder(file));
  const [listing, setListing] = useState({ folder: "", entries: null, error: null });
  const [query, setQuery] = useState("");
  const [found, setFound] = useState(null);
  const rows = useRef(null);
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

  const go = path => { setFolder(path); setQuery(""); };
  // Arrows walk the rows, from the filter into the list and back.
  const walk = (event, from) => {
    if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
    const all = [...(rows.current?.querySelectorAll("[data-explorer-row]") ?? [])];
    const at = from ? all.indexOf(from) : -1;
    const next = event.key === "ArrowDown" ? all[at + 1] : at > 0 ? all[at - 1] : null;
    event.preventDefault();
    if (next) next.focus();
    else if (event.key === "ArrowUp") event.currentTarget.closest("[data-folder-explorer]")?.querySelector("input")?.focus();
  };

  const trail = folderTrail(folder);
  const above = trail.slice(0, Math.max(0, trail.length - SHOWN_FOLDERS));
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
  else body = current.entries.map(entry => <Row key={entry.path} kind={entry.kind} path={entry.path} name={entry.name} active={entry.path === file}
    onClick={() => entry.kind === "directory" ? go(entry.path) : onOpen(entry.path)} />);

  return <div className="flex min-h-0 flex-1 flex-col" data-folder-explorer="">
    <nav aria-label="Folders" className="flex min-w-0 shrink-0 items-center gap-0.5 px-2 pt-2 pb-1 text-xs">
      {above.length ? <>
        <DropdownMenu modal={false}>
          <DropdownMenuTrigger asChild><button type="button" className={CRUMB} aria-label="Folders above">…</button></DropdownMenuTrigger>
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
        <button type="button" className={cn(CRUMB, item.path === folder && "font-medium text-foreground")}
          aria-current={item.path === folder ? "location" : undefined} onClick={() => go(item.path)}>{item.name}</button>
      </Fragment>)}
    </nav>
    <TreeFilterInput label="Filter files" placeholder="Filter files..." value={query} onChange={setQuery} onKeyDown={event => walk(event, null)} />
    <ScrollArea className="min-h-0 flex-1" viewportClassName="p-1" viewportRef={rows}
      viewportProps={{ onKeyDown: event => walk(event, event.target.closest?.("[data-explorer-row]") ?? null) }}>
      {body}
    </ScrollArea>
  </div>;
}
