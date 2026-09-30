import { useCallback, useEffect, useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { Box, FolderOpen, Pin, Search, X } from "lucide-react";
import { Button } from "../primitives/button.jsx";
import { Input } from "../primitives/input.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";

/** A model someone opened: kept by the host, which also says where it is shown from. */
export interface LibraryModel {
  /** The model's identity in the host's library; the absolute path where there is one. */
  path: string;
  name: string;
  /** Where it is, as the person reads it. */
  folder: string;
  /** When it was last opened, in seconds. */
  opened: number;
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

const message = (failure: unknown) => failure instanceof Error ? failure.message : String(failure);

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
  return <span className="cad-recent-thumbnail" ref={element}>{image ? <img src={image} alt="" /> : <Box size={28} strokeWidth={1} aria-hidden="true" />}</span>;
}

/**
 * The models someone opened, to open again: pinned and recent, with pictures, searchable, and,
 * where the host has a chooser, Open Model. Opening is the host's; nothing here waits visibly.
 */
export function ModelLibrary<Model extends LibraryModel>({ library, header, footer, failure = "" }: {
  library: ModelLibrarySource<Model>; header?: ReactNode; footer?: ReactNode;
  /** What the host's own controls failed at, shown where the library's failures are. */
  failure?: string;
}) {
  const [items, setItems] = useState<readonly Model[]>([]);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  // The host's library as it is now: a host may hand a new one each render.
  const current = useRef(library);
  current.current = library;
  const images = useRef(new Map<string, Promise<string | null>>());
  useEffect(() => {
    const refresh = () => current.current.list().then(setItems);
    void refresh().catch(failure => setError(message(failure)));
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
  const searchQuery = items.length ? query : "";
  const shown = filterModels(items, searchQuery);
  const pinned = shown.filter(item => item.pinned);
  const recent = shown.filter(item => !item.pinned);
  const section = (name: string, models: readonly Model[]) => <section className="cad-library-section" aria-label={name}>
    <h2>{name}</h2>
    <ul className="cad-recent-grid">{models.map(item => <li key={item.path} className="cad-recent-item">
      <button className="cad-recent-open" disabled={item.missing} aria-label={`Open ${item.name}`} onClick={() => open(item)}>
        <Thumbnail item={item} load={load} />
        <TooltipHint content={item.path} overflowOnly><span className="cad-recent-name truncate">{item.name}</span></TooltipHint>
        <TooltipHint content={item.folder} overflowOnly><span className="cad-recent-folder truncate">{item.folder}</span></TooltipHint>
      </button>
      <div className="cad-recent-detail">
        <span className="cad-recent-status">{item.missing ? "File unavailable" : new Date(item.opened * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" })}</span>
        <div className="cad-recent-actions">
          <TooltipHint content={item.pinned ? "Unpin" : "Pin"}><Button variant="ghost" size="icon-xs" aria-label={`${item.pinned ? "Unpin" : "Pin"} ${item.name}`} aria-pressed={item.pinned} onClick={() => change(item.pinned ? "unpin" : "pin", item)}><Pin aria-hidden="true" /></Button></TooltipHint>
          <TooltipHint content="Remove from recents"><Button variant="ghost" size="icon-xs" aria-label={`Remove ${item.name} from recents`} onClick={() => change("remove", item)}><X aria-hidden="true" /></Button></TooltipHint>
        </div>
      </div>
    </li>)}</ul>
  </section>;
  const search = items.length > 0 && <div className="cad-library-search"><Search size={14} aria-hidden="true" /><Input className="h-8" type="search" aria-label="Search models" placeholder="Search models" value={query} onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)} /></div>;
  return <main className="cad-library text-ui" aria-label="CAD models">
    {header}
    <div className="cad-library-content">
      {pick || search ? <div className="cad-library-toolbar">
        {pick && <Button size="sm" onClick={pick}><FolderOpen aria-hidden="true" />Open Model</Button>}
        {search}
      </div> : null}
      {(error || failure) && <div className="cad-library-error" role="alert"><p>{error || failure}</p></div>}
      {searchQuery && !shown.length ? <p className="cad-library-empty" role="status">No matching models.</p> : <>
        {pinned.length > 0 && section("Pinned", pinned)}
        {recent.length > 0 ? section("Recent", recent) : !items.length && <section className="cad-library-section" aria-label="Recent"><h2>Recent</h2><p className="cad-library-empty">Open a CAD file to see it here.</p></section>}
      </>}
    </div>
    {footer}
  </main>;
}
