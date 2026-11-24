import { useCallback, useEffect, useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Box, Ellipsis, FolderOpen, LayoutGrid, List, Pin, Search } from "lucide-react";
import { Button } from "../primitives/button.jsx";
import { AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle } from "../primitives/alert-dialog.jsx";
import { ValueDropdown } from "../primitives/value-dropdown.jsx";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "../primitives/dropdown-menu.jsx";
import { Input } from "../primitives/input.jsx";
import { Spinner } from "../primitives/spinner.jsx";
import { useI18n } from "../i18n/index.js";
import type { LibraryLayout } from "../tab-store/tabRecord.js";
import { DocumentGlyph } from "../file-viewer/navigation/DocumentGlyph.jsx";
import { entryMenu } from "../file-viewer/navigation/entry-menu.js";
import type { EntryAction } from "../file-viewer/navigation/index.js";
import type { FileActions } from "../file-viewer/types.js";
import { useControlUsage } from "../usage/controls.js";
import { useNavbarSlots } from "../file-viewer/navbarSlots.js";
import { activityLabel, ageLabel } from "../lib/age.js";
import logo from "../assets/logo-c.svg";

/** A model someone opened: kept by the host, which also says where it is shown from. */
export interface LibraryModel {
  /** The model's identity in the host's library; the absolute path where there is one. */
  path: string;
  /** Its document's id, where the host names one: its picture is read by it. */
  id?: string;
  name: string;
  /** Where it is, as the person reads it. */
  folder: string;
  /** When a page last opened it, in seconds; null for a model no page has opened. */
  opened: number | null;
  /** When it last changed, in seconds: a file's time on disk (null once it is gone), a model's run. */
  updated: number | null;
  /** When its record was first made, in seconds: a model's first run, a file's first open; null for a record from before it was kept. */
  created: number | null;
  pinned: boolean;
  /** Gone from where it was: listed, but not openable. */
  missing: boolean;
  /** A picture's name (its content's): `thumbnail()` reads the picture of the row that names it. */
  thumbnail: string | null;
  /** When the picture was taken, in seconds; null without one. A document updated since has an old one. */
  pictured: number | null;
  /** A file's size on disk, in bytes; null or absent once it is gone, and for a document built from code. */
  size?: number | null;
  /**
   * What it is: a document built from code, a model's or a shape's (`model`, `shape`), which a row
   * deletes -- the engine's copy and its entry; or a CAD file on disk (`file`, and when the host does
   * not say), which a row removes from the list, the file untouched.
   */
  kind?: "file" | "model" | "shape";
}

/** Whether a row deletes the model (a document built from code) rather than removing a file from the list. */
export const deletes = (model: LibraryModel) => model.kind === "model" || model.kind === "shape";

// A file's format as people name it, by its extension; one not here is its extension, upper case.
const FORMATS: Readonly<Record<string, string>> = { step: "STEP", stp: "STEP", stl: "STL", glb: "GLB", gltf: "GLTF", "3mf": "3MF",
  dxf: "DXF", xbf: "XBF", urdf: "URDF", kicad_pcb: "KiCad PCB", kicad_sch: "KiCad SCH" };
/** The formats the viewer opens, under the welcome: names, not language. */
const WELCOME_FORMATS = ["STEP", "STL", "3MF", "GLB", "DXF", "KiCad", "URDF"].join(" · ");
/** What a card's badge and a row's Kind say: a file's format ("STEP", "KiCad PCB"), or `model` for a document built from code. */
export function formatLabel(item: LibraryModel, model: string): string {
  if (deletes(item)) return model;
  const name = item.path.split(/[\\/]/).pop() ?? "";
  const extension = name.includes(".") ? name.slice(name.lastIndexOf(".") + 1).toLowerCase() : "";
  return FORMATS[extension] ?? extension.toUpperCase();
}
/** A size on disk as the Home reads it: bytes, then KB and MB (powers of 1024), in the page's language's digits; "" for none. */
export function sizeLabel(bytes: number | null | undefined, locale?: string): string {
  if (typeof bytes !== "number" || !Number.isFinite(bytes) || bytes < 0) return "";
  const number = (value: number, digits: number) => new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(value);
  if (bytes < 1024) return `${number(bytes, 0)} B`;
  if (bytes < 1024 ** 2) return `${number(Math.round(bytes / 1024), 0)} KB`;
  if (bytes < 1024 ** 3) return `${number(bytes / 1024 ** 2, 1)} MB`;
  return `${number(bytes / 1024 ** 3, 1)} GB`;
}

/** A host's library of models: read, changed and opened through the host. */
export interface ModelLibrarySource<Model extends LibraryModel = LibraryModel> {
  /** Pinned first, then by last activity (`lastActivity`), newest first. */
  list(): Promise<readonly Model[]>;
  /** `delete` for a model's row (`deletes`), `remove` for a file's. */
  change(action: "pin" | "unpin" | "remove" | "delete", model: Model): Promise<readonly Model[]>;
  /**
   * An image URL for a model's thumbnail (the one its `thumbnail` names), or null: the light viewport's
   * picture, which the Home shows in both themes.
   */
  thumbnail(model: Model): Promise<string | null>;
  open(model: Model): Promise<void>;
  /**
   * Open: choose a file with the desktop's own file chooser, and show it. A host on a computer with
   * no chooser has none, and the Home no Open.
   */
  pick?(): Promise<void>;
}

/** A card wants a picture: it has none, or it was updated (a file written, a model run) since it was taken. */
export const wantsPicture = (model: LibraryModel) => !model.missing && (!model.thumbnail
  || (model.updated !== null && model.pictured !== null && model.updated > model.pictured));

/** Whether every word of `query` is in its name, or a file's path: a model is known by its name alone. */
const matches = (item: LibraryModel, words: readonly string[]) => {
  const text = (deletes(item) ? item.name : `${item.name}\n${item.path}`).toLowerCase();
  return words.every(word => text.includes(word));
};
const wordsOf = (query: string) => query.trim().toLowerCase().split(/\s+/).filter(Boolean);

export function filterModels<Model extends LibraryModel>(items: readonly Model[], query: string): Model[] {
  const words = wordsOf(query);
  return items.filter(item => matches(item, words));
}

/** What the type filter over the list shows: everything, the documents built from code, or the files. */
export type LibraryKind = "all" | "models" | "files";
const ofKind = (item: LibraryModel, kind: LibraryKind) => kind === "all" || (kind === "models") === deletes(item);

/** The documents a search and the type filter leave, in the library's order: every model is a card of its own. */
export function shownModels<Model extends LibraryModel>(items: readonly Model[], query: string, kind: LibraryKind = "all"): Model[] {
  const words = wordsOf(query);
  return items.filter(item => ofKind(item, kind) && matches(item, words));
}

const message = (failure: unknown) => failure instanceof Error ? failure.message : String(failure);
/** How often the home reads its list again while it is up. */
const LIST_MS = 2_000;
// The chrome's one scroll region (`primitives/scroll-area.jsx`), as this page uses it.

// A card's or a row's picture, read once it is on screen; and one on screen that wants a picture (`seen`).
// Every picture is the light viewport's, on the model area's light gradient in both themes. A card's
// carries its format's badge (`badge`).
function Thumbnail<Model extends LibraryModel>({ item, load, seen, opening = false, badge = null }: { item: Model; load(item: Model): Promise<string | null>; seen(item: Model): void; opening?: boolean; badge?: string | null }) {
  const { t } = useI18n();
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
      if (name) void load(latest.current.item).then(value => { if (active) setImage(value); }).catch(() => {});
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
  }, [item.path, item.thumbnail, item.missing, item.updated, load]);
  return <span className="cad-library-thumbnail" ref={element}>
    {image ? <img src={image} alt="" /> : <Box strokeWidth={1} aria-hidden="true" />}
    {badge ? <span className="cad-library-format" aria-hidden="true">{badge}</span> : null}
    {opening ? <span className="cad-library-opening"><Spinner aria-label={t("home.openingAria", { name: item.name })} /></span> : null}
  </span>;
}

/** The list's header row: Name, Kind, Size, Updated, Created, over the columns its rows draw (a label each, for the eye: a row names itself). */
function Columns() {
  const { t } = useI18n();
  return <div className="cad-library-columns" aria-hidden="true">
    <span>{t("home.columnName")}</span><span data-column="kind">{t("home.columnKind")}</span><span data-column="size">{t("home.columnSize")}</span>
    <span data-column="updated">{t("home.columnUpdated")}</span><span data-column="created">{t("home.columnCreated")}</span>
  </div>;
}

/** Where the models will be while the list is read: cards (or rows, under their header) in their own places, pulsing. */
function Placeholders({ layout }: { layout: LibraryLayout }) {
  const { t } = useI18n();
  const status = <li className="sr-only" role="status">{t("home.loadingFiles")}</li>;
  return layout === "list"
    ? <div className="cad-library-table"><Columns /><ul className="cad-library-list" aria-label={t("home.filesAria")} aria-busy="true" data-loading="">{status}{[0, 1, 2].map(index => <li key={index} className="cad-library-row" aria-hidden="true">
      <span className="cad-library-open"><span className="cad-library-placeholder" /></span>
    </li>)}</ul></div>
    : <ul className="cad-library-grid" aria-label={t("home.filesAria")} aria-busy="true" data-loading="">{status}{[0, 1, 2, 3].map(index => <li key={index} className="cad-library-card" aria-hidden="true">
      <span className="cad-library-open">
        <span className="cad-library-thumbnail" />
        <span className="cad-library-body"><span className="cad-library-text"><span className="cad-library-placeholder" /><span className="cad-library-placeholder" data-short="" /></span></span>
      </span>
    </li>)}</ul>;
}

/**
 * The host's home: the models opened before, from every view, to open again. The viewer's navbar
 * is over it (its logo's app menu, the host's update and Full size, as over a file); the host's
 * links are that menu's. The page is a centred column (1128px at most, on its own 24px gutters). It
 * starts with its control row, one line of 24px controls: at the
 * left "Recent", the page's heading (the Home's one larger text); at the right the type filter ("All ▾": All, Models, Files),
 * there where models and files are both listed, the search, the grid/list switch and, where the host
 * has a chooser, Open, all there with no models yet too. Then the documents, pinned first, as cards (a picture over the kind's
 * glyph, the name and its last activity with its verb: "Edited 2m ago", "Viewed 16m ago") or as rows
 * (Name, Updated, Created), every
 * model a card and a row of its own: its name, its glyph and its age, never where it was built
 * from. Each card has one ⋯ menu: Open, a file's Copy path and Reveal where the host can (a model
 * has neither), Pin or Unpin, then Delete, which asks first (an AlertDialog saying what
 * goes and what stays on disk) and takes the card off the list at once; a pinned card shows its pin. It is the
 * library and Open: nothing else opens a file from here. It is drawn on the navbar's colour.
 *
 * Nothing waits unseen. While the list is read, placeholder cards (or rows) stand where the models
 * will be. A model being opened shows a spinner over its picture, and the library takes no other
 * open until the host has opened it or failed to. A card on screen that wants a picture
 * (`wantsPicture`) is handed to `picture`, where the viewer draws one out of sight — one card at a
 * time, each once while the page is up — and the list is read again once one is kept.
 */
export function ModelLibrary<Model extends LibraryModel>({ library, layout = "grid", onLayoutChange, picture, fileActions }: {
  library: ModelLibrarySource<Model>;
  /** What the host can do with a file on disk (Copy path, Reveal): each file's menu offers it. */
  fileActions?: FileActions;
  /** Grid or list; the host keeps the choice (the tab's settings). */
  layout?: LibraryLayout;
  onLayoutChange?(layout: LibraryLayout): void;
  /** Draw and keep a model's picture; true once it is kept. */
  picture?(model: Model): Promise<boolean>;
}) {
  const [items, setItems] = useState<readonly Model[] | null>(null);
  const [query, setQueryState] = useState("");
  // What a person does on the home, counted (`usage/controls.js`): a search begun, never what it looks for.
  const usage = useControlUsage();
  const setQuery = (next: string) => { if (!query.trim() && next.trim()) usage.used("home_search"); setQueryState(next); };
  const [error, setError] = useState("");
  const { t, locale } = useI18n();
  // The host's library as it is now: a host may hand a new one each render.
  const current = useRef(library);
  current.current = library;
  const images = useRef(new Map<string, Promise<string | null>>());
  // The same list again is not news: the cards keep their state and are not drawn again.
  const refresh = useCallback(() => current.current.list().then(next =>
    setItems(previous => previous && JSON.stringify(previous) === JSON.stringify(next) ? previous : next)), []);
  // Read on mount, again every couple of seconds while the home is up (a model rebuilt meanwhile
  // is updated later than its picture, and is pictured again), and when the page is shown.
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
  // Once per card and update: a file written or a model run again wants its picture again.
  const seen = useCallback((item: Model) => {
    const key = JSON.stringify([item.path, item.updated]);
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
  const load = useCallback((item: Model) => {
    // A picture is kept by its name, its content's: a new picture of the row is another name.
    const name = String(item.thumbnail);
    let image = images.current.get(name);
    if (!image) {
      image = current.current.thumbnail(item);
      images.current.set(name, image);
    }
    return image;
  }, []);
  const fail = (failure: unknown) => setError(message(failure));
  // The model being opened: the host may take a moment, and a second press must not open twice.
  const [opening, setOpening] = useState<string | null>(null);
  const open = (item: Model) => {
    if (opening) return;
    usage.used("home_open");
    setError("");
    setOpening(item.path);
    void current.current.open(item).catch(fail).finally(() => setOpening(null));
  };
  // Open, at the control row's right end: the host's chooser, where its computer has one.
  const pick = library.pick ? () => { usage.used("home_pick"); setError(""); void current.current.pick?.().catch(fail); } : null;
  const change = (action: "pin" | "unpin" | "remove" | "delete", item: Model) => current.current.change(action, item).then(setItems, fail);
  // Delete, once the person says so: a model's (or a shape's) document and its record, that model
  // alone; a file's record alone, the file kept. The card leaves the list at once.
  const [confirming, setConfirming] = useState<Model | null>(null);
  const [gone, setGone] = useState<ReadonlySet<string>>(() => new Set());
  const remove = (item: Model) => {
    setGone(previous => new Set([...previous, item.path]));
    void change(deletes(item) ? "delete" : "remove", item)
      .finally(() => setGone(previous => { const next = new Set(previous); next.delete(item.path); return next; }));
  };
  const all = (items ?? []).filter(item => !gone.has(item.path));
  const [kind, setKind] = useState<LibraryKind>("all");
  // Home's navbar (`file-viewer/navbarSlots.js`): "Recent" and its count, the search and Open go there, on the grid's
  // column; where there is no navbar they stand in the page's own first row.
  const slots = useNavbarSlots();
  // A narrow navbar (under 700px: `styles/globals.css`) shows the search as its icon until it is pressed.
  const [searchOpen, setSearchOpen] = useState(false);
  // The host lists pinned models first; a search and the type filter keep that order.
  const shown = shownModels(all, query, kind);
  // The type filter is there only where there is something to tell apart: models and files both listed.
  const kinds = all.some(deletes) && all.some(item => !deletes(item));
  const now = Date.now();
  // What the host can do with a card's document: Copy path, Copy link and Reveal for a file on disk;
  // a model is no file, and takes Copy link alone (its page needs no file).
  const fileItems = entryMenu(fileActions?.platform ?? "linux", new Set(Object.keys(fileActions?.perform ?? {}) as EntryAction[]), t);
  const modelItems = fileItems.filter(entry => entry.action === "copy-link");
  const HOME_CONTROLS = { "copy-path": "home_copy_path", "copy-link": "home_copy_link", reveal: "home_reveal" } as const;
  const perform = (action: EntryAction, item: Model) => {
    if (action in HOME_CONTROLS) usage.used(HOME_CONTROLS[action as keyof typeof HOME_CONTROLS]);
    void Promise.resolve(fileActions?.perform?.[action]?.({ path: item.path, kind: "file", ...(item.id ? { id: item.id } : {}) })).catch(fail);
  };
  // A card's pin and its one menu (Open, what the host can do with a file on disk, Pin or Unpin, then
  // Delete), there while the pointer is on the card (Figma's star): the pin toggles, and a pinned
  // card shows it, filled, whatever the pointer does.
  // Pin or Unpin, from the card's pin or its menu: counted alike.
  const pin = (item: Model) => { usage.used(item.pinned ? "home_unpin" : "home_pin"); void change(item.pinned ? "unpin" : "pin", item); };
  const actions = (item: Model) => <div className="cad-library-actions" data-pinned={item.pinned || undefined}>
    <Button variant="ghost" size="icon-xs" className="cad-library-pin" aria-label={t(item.pinned ? "home.unpin" : "home.pin")} aria-pressed={item.pinned}
      onClick={() => pin(item)}><Pin aria-hidden="true" fill={item.pinned ? "currentColor" : "none"} /></Button>
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-xs" aria-label={t("home.actionsAria", { name: item.name })}><Ellipsis aria-hidden="true" /></Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-40">
        <DropdownMenuItem disabled={item.missing} onSelect={() => open(item)}>{t("home.menuOpen")}</DropdownMenuItem>
        {(deletes(item) ? modelItems : fileItems).map(entry => <DropdownMenuItem key={entry.action} onSelect={() => perform(entry.action, item)}>{entry.label}</DropdownMenuItem>)}
        <DropdownMenuItem onSelect={() => pin(item)}>{t(item.pinned ? "home.unpin" : "home.pin")}</DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem variant="destructive" onSelect={() => setConfirming(item)}>{t("home.delete")}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  </div>;
  // What Delete asks first: what goes, and what stays on disk; its words stay while the dialog leaves.
  const lastAsked = useRef<Model | null>(null);
  if (confirming) lastAsked.current = confirming;
  const asking = lastAsked.current;
  const question = asking ? deletes(asking)
    ? { title: t("home.deleteModelTitle", { name: asking.name }), body: t("home.deleteModelBody") }
    : { title: t("home.deleteFileTitle", { name: asking.name }), body: t("home.deleteFileBody") } : null;
  const confirm = <AlertDialog open={Boolean(confirming)} onOpenChange={next => { if (!next) setConfirming(null); }}>
    <AlertDialogContent>
      <AlertDialogHeader>
        <AlertDialogTitle>{question?.title}</AlertDialogTitle>
        <AlertDialogDescription>{question?.body}</AlertDialogDescription>
      </AlertDialogHeader>
      <AlertDialogFooter>
        <AlertDialogCancel onClick={() => usage.used("home_delete_cancel")}>{t("home.cancel")}</AlertDialogCancel>
        <AlertDialogAction variant="destructive" onClick={() => { if (confirming) { usage.used("home_delete"); remove(confirming); } }}>{t("home.delete")}</AlertDialogAction>
      </AlertDialogFooter>
    </AlertDialogContent>
  </AlertDialog>;
  const age = (seconds: number | null) => ageLabel(seconds, now, t, locale);
  const format = (item: Model) => formatLabel(item, t("home.formatModel"));
  // A tile's line: a file's size, then its last activity with its verb, Edited or Viewed, whichever came last.
  const status = (item: Model) => item.missing ? t("home.fileUnavailable")
    : [sizeLabel(item.size, locale), activityLabel(item, now, t, locale)].filter(Boolean).join(" · ");
  // A row's picture is small, 40 by 28, its spinner over it while it is being opened.
  const name = (item: Model) => <span className="cad-library-name">
    <Thumbnail item={item} load={load} seen={seen} opening={opening === item.path} />
    <span className="cad-library-label">{item.name}</span>
  </span>;
  // A row's columns: its kind and size, then its two times with no verb: when it last changed, and when its record was first made.
  const columns = (item: Model) => <>
    <span className="cad-library-status" data-column="kind">{format(item)}</span>
    <span className="cad-library-status" data-column="size">{sizeLabel(item.size, locale) || "—"}</span>
    <span className="cad-library-status" data-column="updated">{item.missing ? t("home.fileUnavailable") : age(item.updated)}</span>
    <span className="cad-library-status" data-column="created">{age(item.created)}</span>
  </>;
  const models = layout === "list"
    ? <div className="cad-library-table"><Columns /><ul className="cad-library-list" aria-label={t("home.filesAria")}>{shown.map(item => <li key={item.path} className="cad-library-row" data-missing={item.missing || undefined} data-opening={opening === item.path || undefined}>
      <div className="cad-library-main">
        <button type="button" className="cad-library-open" disabled={item.missing} aria-label={t("home.openAria", { name: item.name })} aria-busy={opening === item.path || undefined} onClick={() => open(item)}>
          {name(item)}
          {columns(item)}
        </button>
        {actions(item)}
      </div>
    </li>)}</ul></div>
    : <ul className="cad-library-grid" aria-label={t("home.filesAria")}>{shown.map(item => <li key={item.path} className="cad-library-card" data-missing={item.missing || undefined} data-opening={opening === item.path || undefined}>
      <div className="cad-library-main">
        <button type="button" className="cad-library-open" disabled={item.missing} aria-label={t("home.openAria", { name: item.name })} aria-busy={opening === item.path || undefined} onClick={() => open(item)}>
          <Thumbnail item={item} load={load} seen={seen} opening={opening === item.path} badge={format(item)} />
          {/* The caption: the kind's glyph at the left of the name over its size and age. */}
          <span className="cad-library-body">
            <DocumentGlyph model={deletes(item)} path={item.path} className="cad-library-glyph" />
            <span className="cad-library-text">
              <span className="cad-library-label">{item.name}</span>
              <span className="cad-library-status">{status(item)}</span>
            </span>
          </span>
        </button>
        {actions(item)}
      </div>
    </li>)}</ul>;
  // Open, the host's chooser: neutral, as every control of the row is (never a filled primary).
  const openButton = (label: string) => <Button variant="outline" size="xs" className="cad-library-pick h-control gap-1.5 px-2.5 text-ui" onClick={pick ?? undefined}>
    <FolderOpen className="size-4" aria-hidden="true" />{label}</Button>;
  const heading = <h1 className="cad-library-heading" data-library-heading={slots ? "navbar" : "page"}>{t("home.recentFiles")}{items !== null && shown.length ? <span className="cad-library-count">{shown.length}</span> : null}</h1>;
  // The type filter: the one value dropdown (`primitives/value-dropdown.jsx`), drawn as the row's ghost control.
  const kindMenu: ReactNode = kinds ? <ValueDropdown value={kind} label={t("home.kindsAria")} align={slots ? "start" : "end"}
    options={(["all", "models", "files"] as const).map(value => ({ value, label: t(`home.kind.${value}`) }))}
    onChange={value => { if (kind !== value) usage.used(`home_filter_${value as LibraryKind}`); setKind(value as LibraryKind); }}
    className="cad-library-kind min-w-0 w-auto gap-1 border-0 bg-transparent px-2 shadow-none hover:bg-accent dark:bg-transparent"
    triggerProps={{ "aria-label": t("home.kindAria", { kind: t(`home.kind.${kind}`) }) }} /> : null;
  // The search: in a narrow navbar its icon alone until it is pressed (it opens with the keyboard in it), and it goes
  // back to its icon when it is left empty.
  const search = <div className="cad-home-search" data-open={searchOpen || query ? "" : undefined}>
    {slots ? <Button variant="ghost" size="icon-xs" className="cad-home-search-button size-control" aria-label={t("home.searchAria")} aria-expanded={false}
      onClick={event => { const box = event.currentTarget.parentElement; setSearchOpen(true); requestAnimationFrame(() => box?.querySelector("input")?.focus()); }}><Search className="size-4" aria-hidden="true" /></Button> : null}
    <div className="cad-library-search">
      <Search aria-hidden="true" />
      <Input className="h-control text-ui" type="search" aria-label={t("home.searchAria")} placeholder={t("home.searchPlaceholder")} value={query}
        onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)} onBlur={() => { if (!query) setSearchOpen(false); }} />
    </div>
  </div>;
  const layoutSwitch = onLayoutChange ? <div className="cad-library-layout" role="group" aria-label={t("home.layout")}>
    <Button variant="ghost" size="icon-xs" className="size-control" aria-label={t("home.grid")} aria-pressed={layout === "grid"} onClick={() => { usage.used("home_layout_grid"); onLayoutChange("grid"); }}><LayoutGrid className="size-4" aria-hidden="true" /></Button>
    <Button variant="ghost" size="icon-xs" className="size-control" aria-label={t("home.list")} aria-pressed={layout === "list"} onClick={() => { usage.used("home_layout_list"); onLayoutChange("list"); }}><List className="size-4" aria-hidden="true" /></Button>
  </div> : null;
  // A page: it scrolls, with the platform's own scrollbar, only when there is more of it than fits.
  return <div className="cad-library h-full overflow-y-auto text-ui" data-library-layout={layout}>
    <main className="cad-library-content" aria-label={t("home.modelsAria")}>
      {/* Home's controls: in the navbar where there is one (`slots`), else in this row, which keeps the filter and the
          layout either way, 28px, on the grid's column: the row keeps its shape from the first open to the hundredth. */}
      {slots ? <>
        {slots.left ? createPortal(heading, slots.left) : null}
        {slots.right ? createPortal(<>{search}{pick ? openButton(t("home.open")) : null}</>, slots.right) : null}
      </> : null}
      <div className="cad-library-toolbar" data-library-toolbar={slots ? "filters" : "page"}>
        {slots ? (kindMenu ?? <span />) : heading}
        <div className="cad-library-controls">
          {slots ? null : kindMenu}
          {slots ? null : search}
          {layoutSwitch}
          {slots || !pick ? null : openButton(t("home.open"))}
        </div>
      </div>
      {error ? <div className="cad-library-error" role="alert"><p>{error}</p></div> : null}
      {items === null ? <Placeholders layout={layout} />
        : (query || kind !== "all") && all.length && !shown.length ? <p className="cad-library-empty" role="status">{t("home.noMatchingModels")}</p>
          : !all.length ? <div className="cad-library-welcome" data-library-empty="">
            <span className="cad-library-welcome-stage"><img src={logo} alt="" draggable={false} /></span>
            <h2 className="cad-library-welcome-title">{t("home.emptyTitle")}</h2>
            <p className="cad-library-welcome-body">{t("home.emptyBody")}</p>
            {pick ? openButton(t("home.openFile")) : null}
            <p className="cad-library-welcome-formats" aria-hidden="true">{WELCOME_FORMATS}</p>
          </div>
            : models}
      {confirm}
    </main>
  </div>;
}
