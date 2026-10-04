import { useCallback, useEffect, useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { Box, FolderOpen, LayoutGrid, List, Pin, Search, Settings, X } from "lucide-react";
import type { CadWorkspaceService } from "@text-to-cad/core/client";
import { Button } from "../primitives/button.jsx";
import { Input } from "../primitives/input.jsx";
import { Spinner } from "../primitives/spinner.jsx";
import type { LibraryLayout } from "../tab-store/tabRecord.js";
import wordmark from "../assets/logo-texttocad.svg";
import { AppMenu } from "../file-viewer/navigation/AppMenu.jsx";
import { GitHubLink } from "../file-viewer/navigation/NavbarLinks.jsx";
import type { AppSetting } from "../file-viewer/types.js";
import type { ViewerLinks } from "../host/types.js";

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
  /** When the picture was taken, in seconds; null without one. A file changed since has an old one. */
  pictured: number | null;
}

/**
 * Where a model is drawn off screen for its card's picture: the CAD client that reads it, its
 * absolute path, and where the picture is kept once it is drawn.
 */
export interface ModelPictureSource {
  client: CadWorkspaceService;
  file: string;
  keep(png: Blob): Promise<unknown>;
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
   * Choose a model with the desktop's own file chooser: Open. A host on a computer with no chooser
   * has none.
   */
  pick?(): Promise<void>;
  /**
   * Where a model can be drawn for a picture, for a card with none or an old one (`CadViewer` draws
   * it); null for a model the host cannot reach. Absent, a card keeps what it has until a view of
   * the model pictures it.
   */
  pictureFrom?(model: Model): ModelPictureSource | null;
}

/** A card wants a picture: it has none, or its file changed since it was taken. */
export const wantsPicture = (model: LibraryModel) => !model.missing && (!model.thumbnail
  || (model.modified !== null && model.pictured !== null && model.modified > model.pictured));

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
/** How often the home reads its list again while it is up. */
const LIST_MS = 2_000;
// The chrome's one scroll region (`primitives/scroll-area.jsx`), as this page uses it.

// A card's picture, read once the card is on screen; and a card on screen that wants one (`seen`).
function Thumbnail<Model extends LibraryModel>({ item, load, seen, opening = false }: { item: Model; load(name: string): Promise<string | null>; seen(item: Model): void; opening?: boolean }) {
  const element = useRef<HTMLSpanElement>(null);
  const [image, setImage] = useState<string | null>(null);
  const latest = useRef({ item, seen });
  latest.current = { item, seen };
  useEffect(() => {
    let active = true;
    // A new picture replaces the old one once it has loaded, never through the placeholder.
    if (!item.thumbnail || item.missing) setImage(null);
    if (item.missing || !element.current) return;
    const name = item.thumbnail;
    const show = () => {
      if (name) void load(name).then(value => { if (active) setImage(value); }).catch(() => {});
      latest.current.seen(latest.current.item);
    };
    if (typeof IntersectionObserver === "undefined") { show(); return () => { active = false; }; }
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(entry => entry.isIntersecting)) return;
      observer.disconnect();
      show();
    });
    observer.observe(element.current);
    return () => { active = false; observer.disconnect(); };
  }, [item.path, item.thumbnail, item.missing, item.modified, load]);
  return <span className="cad-library-thumbnail" ref={element}>
    {image ? <img src={image} alt="" /> : <Box strokeWidth={1} aria-hidden="true" />}
    {opening ? <span className="cad-library-opening"><Spinner aria-label={`Opening ${item.name}`} /></span> : null}
  </span>;
}

/** Where the models will be while the list is read: cards (or rows) in their own places, pulsing. */
function Placeholders({ layout }: { layout: LibraryLayout }) {
  const status = <li className="sr-only" role="status">Loading files</li>;
  return layout === "list"
    ? <ul className="cad-library-list" aria-label="Files" aria-busy="true" data-loading="">{status}{[0, 1, 2].map(index => <li key={index} className="cad-library-row" aria-hidden="true">
      <span className="cad-library-open"><span className="cad-library-thumbnail" /><span className="cad-library-placeholder" /></span>
    </li>)}</ul>
    : <ul className="cad-library-grid" aria-label="Files" aria-busy="true" data-loading="">{status}{[0, 1, 2, 3].map(index => <li key={index} className="cad-library-card" aria-hidden="true">
      <span className="cad-library-open">
        <span className="cad-library-thumbnail" />
        <span className="cad-library-body"><span className="cad-library-placeholder" /><span className="cad-library-placeholder" data-short="" /></span>
      </span>
    </li>)}</ul>;
}

/**
 * The host's home: the models opened before, from every view, to open again. It has no navbar
 * over it: the TEXTTOCAD wordmark is centred at its top over its byline and the host's links — its update, only when
 * there is one, then GitHub and the cog that opens the app's menu (`AppMenu`, the navbar logo's), then the
 * host's Full size where it shows the view small — then "Recent Files" with its search, its grid/list switch and, where
 * the host has a chooser, Open, all three there with no models yet too; then the models, pinned first, as solid cards (a picture over the
 * name and when the file was edited) or as rows. A card can be pinned (its pin filled); a row can
 * also be removed. With none yet, one empty card opens the host's chooser. It is drawn on the
 * navbar's colour.
 *
 * Nothing waits unseen. While the list is read, placeholder cards (or rows) stand where the models
 * will be. A model being opened shows a spinner over its picture, and the library takes no other
 * open until the host has opened it or failed to. A card on screen that wants a picture
 * (`wantsPicture`) is handed to `picture`, where the viewer draws one out of sight — one card at a
 * time, each once while the page is up — and the list is read again once one is kept.
 */
export function ModelLibrary<Model extends LibraryModel>({ library, layout = "grid", onLayoutChange, failure = "", picture, links, platform, appSettings, update, fullSize, onError }: {
  library: ModelLibrarySource<Model>;
  /** Grid or list; the host keeps the choice (the tab's settings). */
  layout?: LibraryLayout;
  onLayoutChange?(layout: LibraryLayout): void;
  /** What the host's own controls failed at, shown where the library's failures are. */
  failure?: string;
  /** Draw and keep a model's picture; true once it is kept. */
  picture?(model: Model): Promise<boolean>;
  /** The host's links, under the wordmark. */
  links?: ViewerLinks;
  /** The host's `environment.platform`, which Feedback's issue names. */
  platform?: string;
  /** The host's own on/off settings, in the app menu the home's cog opens. */
  appSettings?: readonly AppSetting[];
  /** The host's update button, first in the row under the wordmark, while its install is behind. */
  update?: ReactNode;
  /** The host's Full size button, last in that row, where it shows the view small. */
  fullSize?: ReactNode;
  onError?(error: Error): void;
}) {
  const [items, setItems] = useState<readonly Model[] | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState("");
  // The host's library as it is now: a host may hand a new one each render.
  const current = useRef(library);
  current.current = library;
  const images = useRef(new Map<string, Promise<string | null>>());
  // The same list again is not news: the cards keep their state and are not drawn again.
  const refresh = useCallback(() => current.current.list().then(next =>
    setItems(previous => previous && JSON.stringify(previous) === JSON.stringify(next) ? previous : next)), []);
  // Read on mount, again every couple of seconds while the home is up (a model rebuilt meanwhile
  // is edited later than its picture, and is pictured again), and when the page is shown.
  useEffect(() => {
    void refresh().catch(failure => { setItems([]); setError(message(failure)); });
    const again = () => { void refresh().catch(() => {}); };
    const timer = setInterval(again, LIST_MS);
    document.addEventListener("visibilitychange", again);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", again); };
  }, [refresh]);
  // The cards on screen that want a picture, in the order they came into view, drawn one at a time.
  const draw = useRef(picture);
  draw.current = picture;
  const asked = useRef(new Set<string>());
  const [queue, setQueue] = useState<readonly Model[]>([]);
  // Once per card and edit: a file edited again wants its picture again.
  const seen = useCallback((item: Model) => {
    const key = JSON.stringify([item.path, item.modified]);
    if (!draw.current || asked.current.has(key) || !wantsPicture(item)) return;
    asked.current.add(key);
    setQueue(waiting => [...waiting, item]);
  }, []);
  const drawing = useRef(false);
  useEffect(() => {
    const next = queue[0];
    if (!next || drawing.current || !draw.current) return;
    drawing.current = true;
    const done = (kept: boolean) => {
      drawing.current = false;
      setQueue(waiting => waiting.slice(1));
      if (kept) void refresh().catch(() => {});
    };
    draw.current(next).then(done, () => done(false));
  }, [queue, refresh]);
  const load = useCallback((name: string) => {
    let image = images.current.get(name);
    if (!image) {
      image = current.current.thumbnail(name);
      images.current.set(name, image);
    }
    return image;
  }, []);
  const fail = (failure: unknown) => setError(message(failure));
  // The model being opened: the host may take a moment, and a second press must not open twice.
  const [opening, setOpening] = useState<string | null>(null);
  const open = (item: Model) => {
    if (opening) return;
    setError("");
    setOpening(item.path);
    void current.current.open(item).catch(fail).finally(() => setOpening(null));
  };
  const pick = library.pick ? () => { setError(""); void current.current.pick?.().catch(fail); } : null;
  const change = (action: "pin" | "unpin" | "remove", item: Model) => { void current.current.change(action, item).then(setItems, fail); };
  const all = items ?? [];
  // The host lists pinned models first; a search keeps that order.
  const searchQuery = query;
  const shown = filterModels(all, searchQuery);
  const now = Date.now();
  // A card pins; a row pins and removes.
  const actions = (item: Model, removable: boolean) => <div className="cad-library-actions" data-pinned={item.pinned || undefined}>
    <Button variant="ghost" size="icon-xs" aria-label={`${item.pinned ? "Unpin" : "Pin"} ${item.name}`} aria-pressed={item.pinned} onClick={() => change(item.pinned ? "unpin" : "pin", item)}><Pin aria-hidden="true" fill={item.pinned ? "currentColor" : "none"} /></Button>
    {removable ? <Button variant="ghost" size="icon-xs" aria-label={`Remove ${item.name}`} onClick={() => change("remove", item)}><X aria-hidden="true" /></Button> : null}
  </div>;
  const status = (item: Model) => item.missing ? "File unavailable" : editedLabel(item.modified, now);
  const models = layout === "list"
    ? <ul className="cad-library-list" aria-label="Files">{shown.map(item => <li key={item.path} className="cad-library-row" data-missing={item.missing || undefined} data-opening={opening === item.path || undefined}>
      <button type="button" className="cad-library-open" disabled={item.missing} aria-label={`Open ${item.name}`} aria-busy={opening === item.path || undefined} onClick={() => open(item)}>
        <Thumbnail item={item} load={load} seen={seen} opening={opening === item.path} />
        <span className="cad-library-name">{item.name}</span>
        <span className="cad-library-status">{status(item)}</span>
      </button>
      {actions(item, true)}
    </li>)}</ul>
    : <ul className="cad-library-grid" aria-label="Files">{shown.map(item => <li key={item.path} className="cad-library-card" data-missing={item.missing || undefined} data-opening={opening === item.path || undefined}>
      <button type="button" className="cad-library-open" disabled={item.missing} aria-label={`Open ${item.name}`} aria-busy={opening === item.path || undefined} onClick={() => open(item)}>
        <Thumbnail item={item} load={load} seen={seen} opening={opening === item.path} />
        <span className="cad-library-body">
          <span className="cad-library-name">{item.name}</span>
          <span className="cad-library-status">{status(item)}</span>
        </span>
      </button>
      {actions(item, false)}
    </li>)}</ul>;
  // A page: it scrolls, with the platform's own scrollbar, only when there is more of it than fits.
  return <div className="cad-library h-full overflow-y-auto text-ui" data-library-layout={layout}>
    <main className="cad-library-content" aria-label="CAD models">
      <img className="cad-library-wordmark" src={wordmark} alt="text-to-cad" />
      <p className="cad-library-byline">Build anything. <span>100% open source and free.</span></p>
      {links ? <nav className="cad-library-links" aria-label="CAD links">
        {update}
        <GitHubLink links={links} onError={onError} />
        <AppMenu links={links} appSettings={appSettings} platform={platform} align="center" trigger={
          <Button type="button" variant="ghost" size="icon-xs" aria-label="Settings" data-library-settings=""
            className="size-6 cursor-pointer text-muted-foreground hover:text-foreground data-[state=open]:bg-accent data-[state=open]:text-accent-foreground">
            <Settings className="size-3.5" aria-hidden="true" />
          </Button>} />
        {fullSize}
      </nav> : null}
      <div className="cad-library-toolbar">
        <h1 className="cad-library-heading">Recent Files</h1>
        <div className="cad-library-controls">
          {/* There with no models too: the toolbar keeps its shape from the first open to the hundredth. */}
          <div className="cad-library-search">
            <Search aria-hidden="true" />
            <Input className="h-8" type="search" aria-label="Search models" placeholder="Search" value={query} onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)} />
          </div>
          {onLayoutChange ? <div className="cad-library-layout" role="group" aria-label="Layout">
            <Button variant="ghost" size="icon-sm" aria-label="Grid" aria-pressed={layout === "grid"} onClick={() => onLayoutChange("grid")}><LayoutGrid aria-hidden="true" /></Button>
            <Button variant="ghost" size="icon-sm" aria-label="List" aria-pressed={layout === "list"} onClick={() => onLayoutChange("list")}><List aria-hidden="true" /></Button>
          </div> : null}
          {pick ? <Button size="sm" onClick={pick}><FolderOpen aria-hidden="true" />Open</Button> : null}
        </div>
      </div>
      {(error || failure) ? <div className="cad-library-error" role="alert"><p>{error || failure}</p></div> : null}
      {items === null ? <Placeholders layout={layout} />
        : searchQuery && !shown.length ? <p className="cad-library-empty" role="status">No matching models.</p>
          : !all.length ? (pick
            ? <ul className="cad-library-grid" aria-label="Files"><li className="cad-library-card" data-empty="">
              <button type="button" className="cad-library-open" onClick={pick}>
                <span className="cad-library-thumbnail"><Box strokeWidth={1} aria-hidden="true" /></span>
                <span className="cad-library-body"><span className="cad-library-name">Open File</span></span>
              </button>
            </li></ul>
            : <p className="cad-library-empty">Open a CAD file to see it here.</p>)
            : models}
    </main>
  </div>;
}
