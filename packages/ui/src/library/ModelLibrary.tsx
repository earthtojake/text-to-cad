import { useCallback, useEffect, useRef, useState, type ChangeEvent, type ComponentType, type CSSProperties, type ReactNode } from "react";
import { Box, FolderOpen, LayoutGrid, List, Pin, Search, X } from "lucide-react";
import { Button } from "../primitives/button.jsx";
import { Input } from "../primitives/input.jsx";
import { ScrollArea as ScrollRegion } from "../primitives/scroll-area.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { useSceneBackdrop } from "../renderers/kit/look/useSceneBackdrop.js";
import type { LibraryLayout } from "../tab-store/tabRecord.js";
import wordmark from "../assets/logo-cad.svg";

/** A model someone opened: kept by the host, which also says where it is shown from. */
export interface LibraryModel {
  /** The model's identity in the host's library; the absolute path where there is one. */
  path: string;
  name: string;
  /** Where it is, as the person reads it. */
  folder: string;
  /** When it was last opened, in seconds. */
  opened: number;
  /** When the file was last changed on disk, in seconds; null when it is gone. */
  modified: number | null;
  pinned: boolean;
  /** Gone from where it was: listed, but not openable. */
  missing: boolean;
  /** A picture's name, for `thumbnail()`. */
  thumbnail: string | null;
}

/** A host's library of models: read, changed and opened through the host. */
export interface ModelLibrarySource<Model extends LibraryModel = LibraryModel> {
  /** Pinned first, then most recently opened. */
  list(): Promise<readonly Model[]>;
  change(action: "pin" | "unpin" | "remove", model: Model): Promise<readonly Model[]>;
  /** An image URL for a model's thumbnail, or null. */
  thumbnail(name: string): Promise<string | null>;
  open(model: Model): Promise<void>;
  /**
   * Choose a model with the desktop's own file chooser. A host whose files are browsed in place,
   * beside this page, has none: its files are already there to open.
   */
  pick?(): Promise<void>;
}

export function filterModels<Model extends LibraryModel>(items: readonly Model[], query: string): Model[] {
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean);
  return items.filter(item => words.every(word => item.path.toLowerCase().includes(word)));
}

const MONTHS = { month: "short", day: "numeric" } as const;
/** "Edited 16h ago": how long since the file changed, in the largest unit that is at least one. */
export function editedLabel(modified: number | null, now = Date.now()): string {
  if (modified === null || !Number.isFinite(modified)) return "";
  const seconds = Math.max(0, (now - modified * 1000) / 1000);
  if (seconds < 60) return "Edited just now";
  if (seconds < 3600) return `Edited ${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `Edited ${Math.floor(seconds / 3600)}h ago`;
  if (seconds < 7 * 86400) return `Edited ${Math.floor(seconds / 86400)}d ago`;
  const date = new Date(modified * 1000);
  const sameYear = date.getFullYear() === new Date(now).getFullYear();
  return `Edited ${date.toLocaleDateString(undefined, sameYear ? MONTHS : { ...MONTHS, year: "numeric" })}`;
}

const message = (failure: unknown) => failure instanceof Error ? failure.message : String(failure);
// The chrome's one scroll region (`primitives/scroll-area.jsx`), as this page uses it.
const ScrollArea = ScrollRegion as unknown as ComponentType<{ className?: string; style?: CSSProperties; viewportClassName?: string; children: ReactNode; [data: `data-${string}`]: string }>;

function Thumbnail({ item, load }: { item: LibraryModel; load(name: string): Promise<string | null> }) {
  const element = useRef<HTMLSpanElement>(null);
  const [image, setImage] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    setImage(null);
    if (!item.thumbnail || item.missing || !element.current) return;
    const name = item.thumbnail;
    const show = () => void load(name).then(value => { if (active) setImage(value); }).catch(() => {});
    if (typeof IntersectionObserver === "undefined") { show(); return () => { active = false; }; }
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(entry => entry.isIntersecting)) return;
      observer.disconnect();
      show();
    });
    observer.observe(element.current);
    return () => { active = false; observer.disconnect(); };
  }, [item.thumbnail, item.missing, load]);
  return <span className="cad-library-thumbnail" ref={element}>{image ? <img src={image} alt="" /> : <Box strokeWidth={1} aria-hidden="true" />}</span>;
}

/**
 * The host's home: the models opened before, from every view, to open again. The same page in
 * every app — the CAD wordmark centred at its top, then "Files" with its search, its grid/list
 * switch and, where the host has a chooser, Open Model; then the models, pinned first, as solid
 * cards (a picture over the name and when the file was edited) or as rows. It is drawn on the
 * viewport's own colour, so the page and the model it opens into are one surface.
 *
 * Opening is the host's; nothing here waits visibly.
 */
export function ModelLibrary<Model extends LibraryModel>({ library, colorScheme = "light", layout = "grid", onLayoutChange, failure = "" }: {
  library: ModelLibrarySource<Model>;
  colorScheme?: "light" | "dark";
  /** Grid or list; the host keeps the choice (the tab's settings). */
  layout?: LibraryLayout;
  onLayoutChange?(layout: LibraryLayout): void;
  /** What the host's own controls failed at, shown where the library's failures are. */
  failure?: string;
}) {
  const [items, setItems] = useState<readonly Model[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  const { backdrop } = useSceneBackdrop(colorScheme);
  // The host's library as it is now: a host may hand a new one each render.
  const current = useRef(library);
  current.current = library;
  const images = useRef(new Map<string, Promise<string | null>>());
  useEffect(() => {
    const refresh = () => current.current.list().then(setItems);
    void refresh().catch(failure => { setItems([]); setError(message(failure)); });
    const again = () => { if (document.visibilityState !== "hidden") void refresh().catch(() => {}); };
    document.addEventListener("visibilitychange", again);
    return () => document.removeEventListener("visibilitychange", again);
  }, []);
  const load = useCallback((name: string) => {
    let image = images.current.get(name);
    if (!image) {
      image = current.current.thumbnail(name);
      images.current.set(name, image);
    }
    return image;
  }, []);
  const fail = (failure: unknown) => setError(message(failure));
  const open = (item: Model) => { setError(""); void current.current.open(item).catch(fail); };
  const pick = library.pick ? () => { setError(""); void current.current.pick?.().catch(fail); } : null;
  const change = (action: "pin" | "unpin" | "remove", item: Model) => { void current.current.change(action, item).then(setItems, fail); };
  const all = items ?? [];
  const searchQuery = all.length ? query : "";
  // The host lists pinned models first; a search keeps that order.
  const shown = filterModels(all, searchQuery);
  const now = Date.now();
  const actions = (item: Model) => <div className="cad-library-actions" data-pinned={item.pinned || undefined}>
    <TooltipHint content={item.pinned ? "Unpin" : "Pin"}><Button variant="ghost" size="icon-xs" aria-label={`${item.pinned ? "Unpin" : "Pin"} ${item.name}`} aria-pressed={item.pinned} onClick={() => change(item.pinned ? "unpin" : "pin", item)}><Pin aria-hidden="true" /></Button></TooltipHint>
    <TooltipHint content="Remove"><Button variant="ghost" size="icon-xs" aria-label={`Remove ${item.name}`} onClick={() => change("remove", item)}><X aria-hidden="true" /></Button></TooltipHint>
  </div>;
  const status = (item: Model) => item.missing ? "File unavailable" : editedLabel(item.modified, now);
  const models = layout === "list"
    ? <ul className="cad-library-list" aria-label="Files">{shown.map(item => <li key={item.path} className="cad-library-row" data-missing={item.missing || undefined}>
      <TooltipHint content={item.path}><button type="button" className="cad-library-open" disabled={item.missing} aria-label={`Open ${item.name}`} onClick={() => open(item)}>
        <Thumbnail item={item} load={load} />
        <span className="cad-library-name">{item.name}</span>
        <span className="cad-library-status">{status(item)}</span>
      </button></TooltipHint>
      {actions(item)}
    </li>)}</ul>
    : <ul className="cad-library-grid" aria-label="Files">{shown.map(item => <li key={item.path} className="cad-library-card" data-missing={item.missing || undefined}>
      <TooltipHint content={item.path}><button type="button" className="cad-library-open" disabled={item.missing} aria-label={`Open ${item.name}`} onClick={() => open(item)}>
        <Thumbnail item={item} load={load} />
        <span className="cad-library-body">
          <span className="cad-library-name">{item.name}</span>
          <span className="cad-library-status">{status(item)}</span>
        </span>
      </button></TooltipHint>
      {actions(item)}
    </li>)}</ul>;
  return <ScrollArea className="cad-library h-full text-ui" style={{ "--cad-library-backdrop": backdrop } as CSSProperties}
    viewportClassName="cad-library-viewport" data-library-layout={layout}>
    <main className="cad-library-content" aria-label="CAD models">
      <img className="cad-library-wordmark" src={wordmark} alt="CAD" />
      <div className="cad-library-toolbar">
        <h1 className="cad-library-heading">Files</h1>
        <div className="cad-library-controls">
          {all.length > 0 ? <div className="cad-library-search">
            <Search aria-hidden="true" />
            <Input className="h-8" type="search" aria-label="Search models" placeholder="Search" value={query} onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)} />
          </div> : null}
          {all.length > 0 && onLayoutChange ? <div className="cad-library-layout" role="group" aria-label="Layout">
            <TooltipHint content="Grid"><Button variant="ghost" size="icon-sm" aria-label="Grid" aria-pressed={layout === "grid"} onClick={() => onLayoutChange("grid")}><LayoutGrid aria-hidden="true" /></Button></TooltipHint>
            <TooltipHint content="List"><Button variant="ghost" size="icon-sm" aria-label="List" aria-pressed={layout === "list"} onClick={() => onLayoutChange("list")}><List aria-hidden="true" /></Button></TooltipHint>
          </div> : null}
          {pick ? <Button size="sm" onClick={pick}><FolderOpen aria-hidden="true" />Open Model</Button> : null}
        </div>
      </div>
      {(error || failure) ? <div className="cad-library-error" role="alert"><p>{error || failure}</p></div> : null}
      {items === null ? null
        : searchQuery && !shown.length ? <p className="cad-library-empty" role="status">No matching models.</p>
          : !all.length ? <p className="cad-library-empty">Open a CAD file to see it here.</p>
            : models}
    </main>
  </ScrollArea>;
}
