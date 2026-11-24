import { useCallback, useContext, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ComponentType, type KeyboardEvent, type MouseEvent, type ReactNode, type RefObject } from "react";
import { Dialog as DialogPrimitive } from "radix-ui";
import { ExternalLink, Search } from "lucide-react";
import { ScrollArea as ScrollAreaPrimitive } from "../primitives/scroll-area.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { TreeFilterHighlight, matchIndices } from "../primitives/tree-filter.jsx";
import { DocumentGlyph } from "../file-viewer/navigation/DocumentGlyph.jsx";
import { useViewerMobile } from "../file-viewer/responsive.js";
import { ViewerElementContext, ViewerHostContext } from "../host/context.js";
import type { NavigationTarget, ViewerHost } from "../host/types.js";
import { useI18n } from "../i18n/index.js";
import { FLOATING_SURFACE_CLASS } from "../lib/floatingSurface.js";
import { cn } from "../lib/utils.js";
import { deletes, formatLabel, type LibraryModel, type ModelLabels, type ModelLibrarySource } from "../library/ModelLibrary.js";
import { useControlUsage } from "../usage/controls.js";
import { searchShortcut, isSearchKey } from "./searchKey.js";
import { searchGroups, searchRows, type SearchGroup, type SearchRow } from "./searchRows.js";

// The chrome's one scroll region (`primitives/scroll-area.jsx`), as this card uses it.
const ScrollArea = ScrollAreaPrimitive as unknown as ComponentType<{ viewportRef?: RefObject<HTMLDivElement | null>; className?: string; children?: ReactNode }>;

const slashed = (path: string) => path.replace(/\\/g, "/").replace(/\/+$/, "");

/** Where the focus goes back as the search closes: what had it as it opened (a menu's item: that menu's trigger). */
function returnPoint(active: Element | null): HTMLElement | null {
  if (!(active instanceof HTMLElement)) return null;
  const menu = active.closest<HTMLElement>('[role="menu"]');
  const trigger = menu?.id ? active.ownerDocument.querySelector<HTMLElement>(`[aria-controls="${CSS.escape(menu.id)}"]`) : null;
  return menu ? trigger : active;
}

/** The search's state, held where it is mounted (`CadViewer`): open or not, and what to give the focus back to. */
export interface DocumentSearchState {
  open: boolean;
  /** Open it (⌘K, the app menu's Search documents): the focus goes back where it is now as it closes. */
  show(): void;
  close(): void;
  opener: RefObject<HTMLElement | null>;
}

export function useDocumentSearch(): DocumentSearchState {
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLElement | null>(null);
  const show = useCallback(() => { opener.current = returnPoint(document.activeElement); setOpen(true); }, []);
  const close = useCallback(() => setOpen(false), []);
  return useMemo(() => ({ open, show, close, opener }), [open, show, close]);
}

/** What the search reads as it opens: reading, failed (said, nothing else drawn), or every document, one row each. */
type Read<Model extends LibraryModel> = { status: "reading" } | { status: "failed" } | { status: "ready"; rows: SearchRow<Model>[] };

/** Every word of the query lit where it falls in a name (`TreeFilterHighlight`: the brand's text, medium). */
function Highlight({ text, query }: { text: string; query: string }) {
  const indices = [...new Set(query.trim().split(/\s+/).filter(Boolean).flatMap(word => matchIndices(text, word)))];
  return indices.length ? <TreeFilterHighlight text={text} indices={indices} /> : <>{text}</>;
}

// A row: the control + 16 tall (44px; a phone's 52), its picture the control + 4 tall at 3:2 (32px), on the light
// model area a library picture is taken on, in both themes.
const ROW_CLASS = "relative flex min-h-[calc(var(--cad-control)+16px)] items-center gap-3 rounded-md px-2 text-foreground outline-none";
const PICTURE_CLASS = "relative grid h-[calc(var(--cad-control)+4px)] aspect-[3/2] shrink-0 place-items-center overflow-hidden rounded-control "
  + "bg-[linear-gradient(to_bottom,#f4f5f6,#dfe2e5)] text-[#9aa0a6] shadow-[inset_0_0_0_1px_rgba(0,0,0,.07)]";

/**
 * A document's picture: the library's (`thumbnail()`), read once its row comes on screen in the list (`root`) and
 * kept by its name for as long as the search is mounted; the kind's glyph until it has loaded, and where it has none.
 */
function Picture<Model extends LibraryModel>({ model, load, root }: { model: Model; load(model: Model): Promise<string | null>; root: RefObject<HTMLElement | null> }) {
  const element = useRef<HTMLSpanElement>(null);
  const [image, setImage] = useState<string | null>(null);
  useEffect(() => {
    setImage(null);
    if (!model.thumbnail || model.missing || !element.current) return undefined;
    let live = true;
    const show = () => { void load(model).then(url => { if (live) setImage(url); }, () => {}); };
    if (typeof IntersectionObserver === "undefined") { show(); return () => { live = false; }; }
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(entry => entry.isIntersecting)) return;
      observer.disconnect();
      show();
    }, { root: root.current });
    observer.observe(element.current);
    return () => { live = false; observer.disconnect(); };
  }, [model.path, model.thumbnail, model.missing, load, root]);
  return <span ref={element} className={PICTURE_CLASS} data-search-picture="">
    {image ? <img src={image} alt="" className="absolute inset-0 size-full object-contain p-0.5" draggable={false} />
      : <DocumentGlyph model={deletes(model)} path={model.path} className="size-(--cad-glyph)" strokeWidth={1.5} />}
  </span>;
}

/** A key as the footer writes it: a small bordered key, then what it does. */
function KeyHint({ keys, children }: { keys: string; children: string }) {
  return <span className="flex items-center gap-1">
    <kbd className="inline-flex h-[calc(var(--cad-chip)-2px)] items-center rounded-[4px] border border-border bg-background px-1 font-sans text-tiny font-medium text-muted-foreground">{keys}</kbd>
    {children}
  </span>;
}

export interface DocumentSearchProps<Model extends LibraryModel> {
  search: DocumentSearchState;
  /** The host's library: every document (`list`) and the projects with theirs (`projects`), read as the search opens. */
  library: ModelLibrarySource<Model>;
  /** The host's navigation: a row's own address (`hrefOf`) and Open in new tab (`openBeside`), where it has them. */
  navigation: ViewerHost["navigation"];
  /** The document on screen, by its id and its own path, and the project it is in; none over the home. */
  current?: { id?: string | null; path?: string | null; project?: { id: string; name: string } | null } | null;
  onError?(error: Error): void;
}

/**
 * The search of every document in every project (⌘K, Ctrl+K off a Mac, from anywhere outside Preview; the app menu's
 * Search documents), over a document and over the home alike: a card near the top of the page, about 560px wide, on the
 * floating surface with nothing dimmed behind it (a phone's: a sheet the width of the view under the navbar, as its
 * panel's sheet is). An input with the keyboard, the documents under it, and on a desktop a line of the keys.
 *
 * It reads the library as it opens (`list` and `projects`: one row a document) and says while it reads, when the
 * read failed and when nothing matches. With nothing typed it lists the project of the document on screen (with no
 * project, the latest documents); typing finds as the home's search does (every word in the name, or in a file's
 * path), the project on screen's first ("In <project>"), then the rest ("Other projects"), at most `SEARCH_LIMIT`
 * rows drawn, and a line saying how many more there are. A row is its picture (`thumbnail`, read for the rows on
 * screen, the kind's glyph until then), its name and, at its right, its kind in the project on screen, else its
 * project's name ("Standalone" for one in none); the document on screen's row is marked and opens nothing.
 *
 * The input is a combobox over a listbox (the active row is its `aria-activedescendant`), so the focus never leaves it
 * and typing always lands there: Up and Down move, Home and End go to the ends, Enter opens the row in this view and
 * ⌘Enter (Ctrl+Enter) beside it, where the host can (`openBeside`). A click opens a row here; where the host gives it
 * an address (`hrefOf`) the row is a real link, so a modified or middle click, or the link's own menu, is the
 * browser's; where it can open beside, the row under the pointer or the keys shows a small Open in new tab button at its
 * right end. A row opens through the library's own `open` (as the home's cards do: the host keeps the card's name
 * for the navbar until the document is read). Escape, a press outside or a pick closes it, the focus going back
 * where it was. Counted: `search_open`, `search_pick`, `search_new_tab`; never what was typed.
 */
export function DocumentSearch<Model extends LibraryModel>({ search, library, navigation, current = null, onError }: DocumentSearchProps<Model>) {
  const { t } = useI18n();
  const usage = useControlUsage();
  const mobile = useViewerMobile();
  const viewerElement = useContext(ViewerElementContext);
  const ids = useId();
  const listId = `${ids}-list`;
  const optionId = (index: number) => `${ids}-row-${index}`;
  const { open, close, opener } = search;
  const source = useRef(library);
  source.current = library;
  const input = useRef<HTMLInputElement>(null);
  const viewport = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [read, setRead] = useState<Read<Model>>({ status: "reading" });
  const [active, setActive] = useState(-1);
  const platform = useContext(ViewerHostContext)?.environment?.platform;

  // Read as it opens, every time it opens: a model built since is listed. A read of the projects that fails leaves the
  // documents opened before; a read of those that fails is said.
  useEffect(() => {
    if (!open) return undefined;
    usage.used("search_open");
    setQuery("");
    setRead({ status: "reading" });
    let live = true;
    const projects = source.current.projects ? source.current.projects().catch(() => []) : Promise.resolve([]);
    Promise.all([source.current.list(), projects]).then(([list, found]) => {
      if (live) setRead({ status: "ready", rows: searchRows(list, found) });
    }, () => { if (live) setRead({ status: "failed" }); });
    return () => { live = false; };
  }, [open, usage]);

  // A picture is kept by its name (its content's): read once while the search is mounted.
  const pictures = useRef(new Map<string, Promise<string | null>>());
  const loadPicture = useCallback((model: Model) => {
    const name = String(model.thumbnail);
    let image = pictures.current.get(name);
    if (!image) {
      image = source.current.thumbnail(model).catch(() => null);
      pictures.current.set(name, image);
    }
    return image;
  }, []);

  const project = current?.project ?? null;
  const shown = useMemo(() => (read.status === "ready" ? searchGroups(read.rows, { query, project: project?.id ?? null }) : { groups: [] as SearchGroup<Model>[], total: 0 }),
    [read, query, project?.id]);
  const rows = useMemo(() => shown.groups.flatMap(group => group.rows.map(row => ({ row, group: group.id }))), [shown]);
  const drawn = rows.length;
  // The document on screen's row, by its id or its own path: marked, and never opened onto itself.
  const currentId = current?.id || null, currentPath = current?.path ? slashed(current.path) : null;
  const onScreen = useCallback((row: SearchRow<Model>) => Boolean((currentId && row.model.id === currentId)
    || (currentPath && slashed(row.model.path) === currentPath)), [currentId, currentPath]);
  const openable = useCallback((row: SearchRow<Model>) => !row.model.missing && !onScreen(row), [onScreen]);
  // The keys' row: the first that opens, each time what is listed changes.
  useEffect(() => { setActive(rows.findIndex(entry => openable(entry.row))); }, [rows, openable]);
  useEffect(() => {
    if (active < 0) return;
    document.getElementById(optionId(active))?.scrollIntoView?.({ block: "nearest" });
  }, [active]);

  const target = (row: SearchRow<Model>): NavigationTarget => ({ document: row.key });
  const beside = navigation.openBeside ?? null;
  const besideLabel = beside?.kind === "browser" ? t("search.openBrowser") : t("search.openNewTab");
  const pick = (row: SearchRow<Model>) => {
    if (!openable(row)) return;
    usage.used("search_pick");
    close();
    void source.current.open(row.model).catch(error => onError?.(error instanceof Error ? error : new Error(String(error))));
  };
  const openBeside = (row: SearchRow<Model>) => {
    if (!beside || row.model.missing) return;
    usage.used("search_new_tab");
    close();
    void Promise.resolve(beside.open(target(row))).catch(error => onError?.(error instanceof Error ? error : new Error(String(error))));
  };
  const step = (from: number, by: 1 | -1) => {
    for (let at = from + by; at >= 0 && at < drawn; at += by) if (openable(rows[at].row)) return at;
    return from;
  };
  const onKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    if (isSearchKey(event.nativeEvent, platform)) { event.preventDefault(); close(); return; }
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      setActive(now => step(now, event.key === "ArrowDown" ? 1 : -1));
    } else if (event.key === "Home" || event.key === "End") {
      event.preventDefault();
      setActive(now => {
        const end = event.key === "Home" ? step(-1, 1) : step(drawn, -1);
        return end >= 0 && end < drawn ? end : now;
      });
    } else if (event.key === "Enter" && !event.nativeEvent.isComposing) {
      event.preventDefault();
      const row = rows[active]?.row;
      if (!row) return;
      const modified = platform === "darwin" ? event.metaKey : event.ctrlKey;
      if (modified) openBeside(row);
      else pick(row);
    }
  };
  // Typing always lands in the input, wherever a press left the focus inside the card.
  const onCardKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (event.target === input.current || event.key.length !== 1 || event.metaKey || event.ctrlKey || event.altKey) return;
    input.current?.focus();
  };
  // A row's link: a plain click opens it here; a modified or middle click is the browser's (a new tab), counted.
  const onRowClick = (event: MouseEvent<HTMLElement>, row: SearchRow<Model>, href: string | null) => {
    if (href && (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0)) {
      usage.used("search_new_tab");
      return;
    }
    event.preventDefault();
    pick(row);
  };

  // A phone's sheet stands under the navbar, as its panel's sheet does; measured while it is open.
  const [top, setTop] = useState<number | null>(null);
  useLayoutEffect(() => {
    const bar = mobile && open ? viewerElement?.current?.querySelector("[data-viewer-navbar]") : null;
    if (!bar) { setTop(null); return undefined; }
    const measure = () => setTop(Math.round(bar.getBoundingClientRect().bottom));
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(bar);
    return () => observer.disconnect();
  }, [mobile, open, viewerElement]);

  const labels: ModelLabels = { model: t("search.kindModel"), part: t("search.kindPart"), assembly: t("search.kindAssembly") };
  const heading = (group: SearchGroup<Model>) => group.id === "here" ? t("search.inProject", { name: project?.name ?? "" })
    : group.id === "other" ? t("search.otherProjects") : group.id === "recent" ? t("search.recent") : null;
  const detail = (row: SearchRow<Model>, group: SearchGroup<Model>["id"]) => onScreen(row) ? t("search.current")
    : group === "here" ? formatLabel(row.model, labels) : row.project?.name ?? t("search.standalone");
  const listed = read.status === "ready" && drawn > 0;
  const status = read.status === "reading" ? t("search.reading") : read.status === "failed" ? t("search.failed")
    : drawn === 0 ? (query.trim() ? t("search.nothingFound", { query: query.trim() }) : t("search.empty")) : null;
  const modifier = platform === "darwin" ? "⌘" : "Ctrl+";
  let index = -1;

  return <DialogPrimitive.Root open={open} onOpenChange={next => { if (!next) close(); }}>
    <DialogPrimitive.Portal>
      <DialogPrimitive.Content aria-describedby={undefined} data-document-search="" data-search-layout={mobile ? "sheet" : "card"}
        onOpenAutoFocus={event => { event.preventDefault(); input.current?.focus(); }}
        onCloseAutoFocus={event => {
          const back = opener.current;
          if (back?.isConnected) { event.preventDefault(); back.focus({ preventScroll: true }); }
        }}
        onKeyDown={onCardKeyDown}
        style={mobile && top !== null ? { top } : undefined}
        className={cn(FLOATING_SURFACE_CLASS, "fixed z-50 flex flex-col overflow-hidden text-ui outline-none",
          "data-[state=open]:animate-in data-[state=open]:fade-in-0 data-[state=closed]:animate-out data-[state=closed]:fade-out-0 motion-reduce:animate-none",
          mobile ? "inset-x-0 bottom-0 top-0 rounded-none border-x-0 border-b-0"
            : "top-[min(6rem,12vh)] left-1/2 w-[calc(100%-2rem)] max-w-[35rem] -translate-x-1/2 rounded-[10px] data-[state=open]:zoom-in-95")}>
        <DialogPrimitive.Title className="sr-only">{t("search.title")}</DialogPrimitive.Title>
        {/* The input's row: the magnifier, the input, and on a desktop the key that opened it. */}
        <div className="flex h-[calc(var(--cad-control)+16px)] shrink-0 items-center gap-2 border-b border-border px-3" data-search-field="">
          <Search className="size-(--cad-glyph) shrink-0 text-muted-foreground" aria-hidden="true" />
          <input ref={input} type="text" role="combobox" aria-label={t("search.label")} aria-expanded={listed} aria-controls={listId}
            aria-autocomplete="list" aria-activedescendant={listed && active >= 0 ? optionId(active) : undefined}
            placeholder={t("search.placeholder")} spellCheck={false} autoComplete="off" value={query}
            onChange={event => setQuery(event.target.value)} onKeyDown={onKeyDown}
            className="h-full min-w-0 flex-1 bg-transparent text-ui text-foreground outline-none placeholder:text-muted-foreground" />
          {mobile ? null : <kbd className="inline-flex h-[calc(var(--cad-chip)-2px)] shrink-0 items-center rounded-[4px] border border-border bg-background px-1 font-sans text-tiny font-medium text-muted-foreground">
            {searchShortcut(platform)}</kbd>}
        </div>
        <ScrollArea viewportRef={viewport} className={mobile ? "flex-1" : "max-h-[min(28rem,calc(100vh-14rem))]"}>
          <div role="listbox" id={listId} aria-label={t("search.results")} aria-busy={read.status === "reading" || undefined} className="flex flex-col p-1" data-search-list="">
            {read.status === "reading" ? [0, 1, 2].map(at => <div key={at} aria-hidden="true" className={ROW_CLASS} data-search-placeholder="">
              <span className={cn(PICTURE_CLASS, "motion-safe:animate-pulse")} />
              <span className="h-2 rounded-full bg-muted-foreground/20 motion-safe:animate-pulse" style={{ width: `${[48, 36, 56][at]}%` }} />
            </div>) : null}
            {shown.groups.map(group => {
              const label = heading(group);
              const headingId = `${ids}-${group.id}`;
              return <div key={group.id} role="group" aria-labelledby={label ? headingId : undefined} aria-label={label ? undefined : t("search.results")} data-search-group={group.id}>
                {label ? <div id={headingId} role="presentation" className="flex h-control items-end truncate px-2 pb-1 text-tiny text-muted-foreground" data-search-heading="">{label}</div> : null}
                {group.rows.map(row => {
                  index += 1;
                  const at = index;
                  const here = onScreen(row);
                  const opens = openable(row);
                  const href = opens ? navigation.hrefOf?.(target(row)) ?? null : null;
                  const lit = at === active;
                  const besideShown = Boolean(beside && !row.model.missing);
                  const Element = href ? "a" : "div";
                  return <div key={row.key} role="none" className="group/row relative">
                    <Element id={optionId(at)} role="option" tabIndex={-1} aria-selected={lit} aria-disabled={opens ? undefined : true}
                      aria-current={here ? "page" : undefined} {...(href ? { href } : null)}
                      onMouseDown={(event: MouseEvent) => { if (event.button === 0) event.preventDefault(); }}
                      onPointerMove={() => { if (opens && !lit) setActive(at); }}
                      onClick={(event: MouseEvent<HTMLElement>) => { if (opens) onRowClick(event, row, href); else event.preventDefault(); }}
                      onAuxClick={(event: MouseEvent<HTMLElement>) => { if (href && event.button === 1) usage.used("search_new_tab"); }}
                      className={cn(ROW_CLASS, opens ? "cursor-pointer" : "cursor-default", lit && "bg-accent", here && "bg-brand-subtle",
                        row.model.missing && "opacity-50", besideShown && "pr-[calc(var(--cad-icon-button)+12px)]")}
                      data-search-row="" data-search-key={row.key}>
                      <Picture model={row.model} load={loadPicture} root={viewport} />
                      <span className="min-w-0 flex-1 truncate"><Highlight text={row.model.name} query={query} /></span>
                      <span className={cn("shrink-0 truncate text-xs text-muted-foreground", besideShown && !here && "group-hover/row:invisible", besideShown && lit && !here && "invisible")}
                        data-search-detail="">{detail(row, group.id)}</span>
                    </Element>
                    {besideShown && !here ? <TooltipHint content={besideLabel} side="left">
                      <button type="button" tabIndex={-1} aria-hidden="true" data-search-beside=""
                        onMouseDown={event => event.preventDefault()} onClick={() => openBeside(row)}
                        className={cn("absolute top-1/2 right-2 grid size-icon-button -translate-y-1/2 place-items-center rounded-md text-muted-foreground opacity-0 transition-opacity",
                          "hover:bg-accent hover:text-foreground group-hover/row:opacity-100", lit && "opacity-100")}>
                        <ExternalLink className="size-3.5" aria-hidden="true" />
                      </button>
                    </TooltipHint> : null}
                  </div>;
                })}
              </div>;
            })}
          </div>
          {status ? <p role="status" className="px-3 py-6 text-center text-muted-foreground" data-search-status={read.status === "ready" ? "empty" : read.status}>
            {status}</p> : null}
          {read.status === "ready" && shown.total > drawn ? <p role="status" className="px-3 pt-1 pb-3 text-center text-tiny text-muted-foreground" data-search-more="">
            {t("search.more", { shown: drawn, total: shown.total })}</p> : null}
        </ScrollArea>
        {mobile ? null : <div className="flex h-[calc(var(--cad-control)+8px)] shrink-0 items-center gap-4 border-t border-border bg-sidebar px-3 text-tiny text-muted-foreground" data-search-keys="">
          <KeyHint keys="↑↓">{t("search.keyMove")}</KeyHint>
          <KeyHint keys="↵">{t("search.keyOpen")}</KeyHint>
          {beside ? <KeyHint keys={`${modifier}↵`}>{besideLabel}</KeyHint> : null}
          <span className="ml-auto"><KeyHint keys="Esc">{t("search.keyClose")}</KeyHint></span>
        </div>}
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  </DialogPrimitive.Root>;
}
