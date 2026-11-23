import { useCallback, useEffect, useRef, useState, type ChangeEvent, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Box, ChevronDown, Ellipsis, Folder, FolderOpen, LayoutGrid, List, Pin, Search } from "lucide-react";
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
import { activityLabel, ageLabel, lastActivity } from "../lib/age.js";
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
  /** The id of the project it is in (`LibraryProject`): its section's; none, a standalone document's. */
  project?: string | null;
}

/** A folder a person opened as a project, with its documents, as the host lists it (a CAD host's `CadProject`). */
export interface LibraryProject<Model extends LibraryModel = LibraryModel> {
  id: string;
  /** Its folder's name. */
  name: string;
  /** Its folder, `/`-separated. */
  root: string;
  /** When it was last opened as a project, in seconds. */
  opened: number | null;
  /** Its folder is gone: listed, until the person removes it. */
  missing: boolean;
  /** Its models, then its CAD files, as the host lists them. */
  documents: readonly Model[];
  /** The host's walk of its folder stopped early: not every file of it is listed. */
  truncated?: boolean;
}

/** What came of Import's Folder: the project the folder chosen is, whether it was made now, and that folder. */
export interface ImportedProject {
  project: { id: string; name: string; root: string };
  /** False: the folder was a project already, or is inside the one answered. */
  made: boolean;
  /** The folder the person chose, `/`-separated. */
  folder: string;
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
   * Import's File: choose a file with the desktop's own file chooser, and show it. A host on a computer with
   * no chooser has none, and the Home's Import no File.
   */
  pick?(): Promise<void>;
  /** The projects, the latest activity first, each with its documents. A host with none lists none. */
  projects?(): Promise<readonly LibraryProject<Model>[]>;
  /**
   * Import's Folder: a folder chosen with the desktop's chooser -- opening in `start` where one is named -- opened as
   * a project; null when the person cancels. A host on a computer with no chooser has none.
   */
  importFolder?(start?: string): Promise<ImportedProject | null>;
  /** Remove from CAD: the project's record alone, nothing in its folder. The projects as they now are. */
  removeProject?(project: LibraryProject<Model>): Promise<readonly LibraryProject<Model>[]>;
}

/** How many of a project's documents its section shows before its Show all. */
export const PROJECT_TILES = 8;

/**
 * A project's documents as its section lists them: pinned first, then its models before its files, each by last
 * activity (when it was last opened or changed), newest first; the host's order where two tie.
 */
export function projectOrder<Model extends LibraryModel>(documents: readonly Model[]): Model[] {
  return documents.map((item, index) => ({ item, index })).sort((a, b) => Number(b.item.pinned) - Number(a.item.pinned)
    || Number(deletes(b.item)) - Number(deletes(a.item)) || (lastActivity(b.item) ?? 0) - (lastActivity(a.item) ?? 0) || a.index - b.index)
    .map(({ item }) => item);
}

/** `path` as the home says it: from `~` where it is in the person's home folder (`home`). */
export function tildePath(path: string, home?: string | null): string {
  const base = (home ?? "").replace(/\\/g, "/").replace(/\/+$/, "");
  const shown = path.replace(/\\/g, "/");
  if (!base) return shown;
  return shown === base ? "~" : shown.startsWith(`${base}/`) ? `~${shown.slice(base.length)}` : shown;
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
 * The host's home: the projects, each with its documents, then the standalone documents opened before, from every
 * view, to open again. The viewer's navbar is over it (its logo's app menu, the host's update and Full size, as over a
 * file); the host's links are that menu's. The page is a centred column (1128px at most, on its own 24px gutters). It
 * starts with its control row, one line of 24px controls: at the left "Home", the page's heading (the Home's one larger
 * text); at the right the type filter ("All ▾": All, Models, Files), there where models and files are both listed, the
 * search, the grid/list switch and, where the host has a chooser, Import (its File and its Folder), all there with
 * nothing yet too.
 *
 * Then each project (`projects`: a folder a person opened as one), the latest activity first: a section headed by its
 * name, its folder (from `~`) and its ⋯ (Copy path, Reveal, Remove from CAD, which forgets the project and nothing on
 * disk), then its documents -- pinned first, its models, then its files, each by last activity -- `PROJECT_TILES` of
 * them until its Show all. Then the standalone documents, those in no project, pinned first, under "Standalone" where
 * there are projects. Each document is a card (a picture over the kind's glyph, the name and its last activity with its
 * verb: "Edited 2m ago", "Viewed 16m ago") or a row (Name, Updated, Created): its name, its glyph and its age, never
 * where it was built from. Each has one ⋯ menu: Open, a file's Copy path and Reveal where the host can (a model has
 * neither), Pin or Unpin, then Delete, which asks first (an AlertDialog saying what goes and what stays on disk) and
 * takes the card off the list at once; a pinned card shows its pin. A project's file is listed for being in its folder:
 * it has no Delete, and a Pin once a page has opened it. A search and the type filter narrow every section, a section
 * with nothing left gone. It is drawn on the navbar's colour.
 *
 * `focus` (a project's id: the navbar's project name, pressed) brings that project's section into view, marked, as
 * Import's Folder does the project it opened, with a line saying what came of it.
 *
 * Nothing waits unseen. While the list is read, placeholder cards (or rows) stand where the documents will be. A
 * document being opened shows a spinner over its picture, and the library takes no other open until the host has
 * opened it or failed to. A card on screen that wants a picture (`wantsPicture`) is handed to `picture`, where the
 * viewer draws one out of sight — one card at a time, each once while the page is up — and the list is read again
 * once one is kept.
 */
export function ModelLibrary<Model extends LibraryModel>({ library, layout = "grid", onLayoutChange, picture, fileActions, focus = null, home = null }: {
  library: ModelLibrarySource<Model>;
  /** What the host can do with a file on disk (Copy path, Reveal): each file's menu offers it, and each project's. */
  fileActions?: FileActions;
  /** Grid or list; the host keeps the choice (the tab's settings). */
  layout?: LibraryLayout;
  onLayoutChange?(layout: LibraryLayout): void;
  /** Draw and keep a model's picture; true once it is kept. */
  picture?(model: Model): Promise<boolean>;
  /** The project to bring into view: the navbar's project name was pressed over one of its documents. */
  focus?: string | null;
  /** The person's home folder, where the host knows it: a project's folder is said from `~` in it. */
  home?: string | null;
}) {
  const [items, setItems] = useState<readonly Model[] | null>(null);
  const [projects, setProjects] = useState<readonly LibraryProject<Model>[] | null>(null);
  const [query, setQueryState] = useState("");
  // What a person does on the home, counted (`usage/controls.js`): a search begun, never what it looks for.
  const usage = useControlUsage();
  const setQuery = (next: string) => { if (!query.trim() && next.trim()) usage.used("home_search"); setQueryState(next); };
  const [error, setError] = useState("");
  // What came of the last Import's Folder or Remove from CAD, in a line under the controls.
  const [note, setNote] = useState("");
  const { t, locale } = useI18n();
  // The host's library as it is now: a host may hand a new one each render.
  const current = useRef(library);
  current.current = library;
  const images = useRef(new Map<string, Promise<string | null>>());
  // The same list again is not news: the cards keep their state and are not drawn again. The projects are read with
  // it (`readProjects`); a read of them that fails keeps the ones shown.
  const readProjects = useCallback(() => (current.current.projects ? current.current.projects().then(found => found, () => undefined)
    : Promise.resolve([])).then(found => {
    if (found !== undefined) setProjects(previous => previous && JSON.stringify(previous) === JSON.stringify(found) ? previous : found);
  }), []);
  const refresh = useCallback(() => Promise.all([current.current.list(), readProjects()]).then(([next]) => {
    setItems(previous => previous && JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
  }), [readProjects]);
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
  // The document being opened: the host may take a moment, and a second press must not open twice.
  const [opening, setOpening] = useState<string | null>(null);
  const open = (item: Model) => {
    if (opening) return;
    usage.used("home_open");
    setError("");
    setOpening(item.path);
    void current.current.open(item).catch(fail).finally(() => setOpening(null));
  };
  // The project brought into view and marked: the one the host names (`focus`), or the one Import's Folder opened.
  const [focused, setFocused] = useState<string | null>(focus);
  useEffect(() => { if (focus) setFocused(focus); }, [focus]);
  const sections = useRef(new Map<string, HTMLElement>());
  // Once its section is drawn: a project Import's Folder just opened is listed a moment after it is named.
  const focusListed = Boolean(focused && projects?.some(project => project.id === focused));
  useEffect(() => {
    if (focused && focusListed) sections.current.get(focused)?.scrollIntoView?.({ block: "start" });
  }, [focused, focusListed]);
  // Import, at the control row's right end: the host's chooser of a file (shown as it is chosen) or of a folder (opened
  // as a project, brought into view and said), where its computer has one.
  const importFile = library.pick ? () => { usage.used("home_pick"); setError(""); setNote(""); void current.current.pick?.().catch(fail); } : null;
  const importFolder = library.importFolder ? () => {
    usage.used("home_import_folder");
    setError("");
    setNote("");
    void current.current.importFolder?.().then(imported => {
      if (!imported) return;
      const { project, made, folder } = imported;
      setFocused(project.id);
      setNote(made ? t("home.projectMade", { name: project.name })
        : folder.replace(/\/+$/, "") === project.root.replace(/\/+$/, "") ? t("home.projectAgain", { name: project.name })
          : t("home.projectInside", { name: folder.split("/").filter(Boolean).pop() ?? folder, project: project.name }));
      return refresh();
    }).catch(fail);
  } : null;
  // A change answers the library as it now is; a project's documents, which it may have changed too, are read again.
  const change = (action: "pin" | "unpin" | "remove" | "delete", item: Model) => current.current.change(action, item)
    .then(next => { setItems(next); void readProjects(); }, fail);
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
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(() => new Set());
  // Home's navbar (`file-viewer/navbarSlots.js`): its heading, the search and Import go there, on the grid's
  // column; where there is no navbar they stand in the page's own first row.
  const slots = useNavbarSlots();
  // A narrow navbar (under 700px: `styles/globals.css`) shows the search as its icon until it is pressed.
  const [searchOpen, setSearchOpen] = useState(false);
  const filtering = Boolean(query.trim()) || kind !== "all";
  // Each project's documents, and the standalone ones: those of no project the home lists.
  const known = new Set((projects ?? []).map(project => project.id));
  const projectSections = (projects ?? []).map(project => {
    const documents = projectOrder(project.documents.filter(item => !gone.has(item.path)));
    return { project, documents, matching: shownModels(documents, query, kind) };
  });
  const standalone = all.filter(item => !item.project || !known.has(item.project));
  // The host lists pinned documents first; a search and the type filter keep that order.
  const shown = shownModels(standalone, query, kind);
  // The type filter is there only where there is something to tell apart: models and files both listed.
  const everything = [...all, ...projectSections.flatMap(section => section.documents)];
  const kinds = everything.some(deletes) && everything.some(item => !deletes(item));
  const now = Date.now();
  // What the host can do with a card's document: Copy path, Copy link and Reveal for a file on disk;
  // a model is no file, and takes Copy link alone (its page needs no file). A project's folder: Copy path and Reveal.
  const fileItems = entryMenu(fileActions?.platform ?? "linux", new Set(Object.keys(fileActions?.perform ?? {}) as EntryAction[]), t);
  const modelItems = fileItems.filter(entry => entry.action === "copy-link");
  const folderItems = fileItems.filter(entry => entry.action === "copy-path" || entry.action === "reveal");
  const HOME_CONTROLS = { "copy-path": "home_copy_path", "copy-link": "home_copy_link", reveal: "home_reveal" } as const;
  const PROJECT_CONTROLS = { "copy-path": "home_project_copy_path", reveal: "home_project_reveal" } as const;
  const perform = (action: EntryAction, item: Model) => {
    if (action in HOME_CONTROLS) usage.used(HOME_CONTROLS[action as keyof typeof HOME_CONTROLS]);
    void Promise.resolve(fileActions?.perform?.[action]?.({ path: item.path, kind: "file", ...(item.id ? { id: item.id } : {}) })).catch(fail);
  };
  // A card's pin and its one menu (Open, what the host can do with a file on disk, Pin or Unpin, then
  // Delete), there while the pointer is on the card (Figma's star): the pin toggles, and a pinned
  // card shows it, filled, whatever the pointer does. A project's file has no Delete (its folder lists it), and a Pin
  // once a page has opened it (its record).
  // Pin or Unpin, from the card's pin or its menu: counted alike.
  const pin = (item: Model) => { usage.used(item.pinned ? "home_unpin" : "home_pin"); void change(item.pinned ? "unpin" : "pin", item); };
  const actions = (item: Model, inProject: boolean) => {
    const pinnable = !inProject || deletes(item) || item.pinned || item.opened !== null;
    const deletable = !inProject || deletes(item);
    return <div className="cad-library-actions" data-pinned={item.pinned || undefined}>
      {pinnable ? <Button variant="ghost" size="icon-xs" className="cad-library-pin" aria-label={t(item.pinned ? "home.unpin" : "home.pin")} aria-pressed={item.pinned}
        onClick={() => pin(item)}><Pin aria-hidden="true" fill={item.pinned ? "currentColor" : "none"} /></Button> : null}
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon-xs" aria-label={t("home.actionsAria", { name: item.name })}><Ellipsis aria-hidden="true" /></Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="min-w-40">
          <DropdownMenuItem disabled={item.missing} onSelect={() => open(item)}>{t("home.menuOpen")}</DropdownMenuItem>
          {(deletes(item) ? modelItems : fileItems).map(entry => <DropdownMenuItem key={entry.action} onSelect={() => perform(entry.action, item)}>{entry.label}</DropdownMenuItem>)}
          {pinnable ? <DropdownMenuItem onSelect={() => pin(item)}>{t(item.pinned ? "home.unpin" : "home.pin")}</DropdownMenuItem> : null}
          {deletable ? <>
            <DropdownMenuSeparator />
            <DropdownMenuItem variant="destructive" onSelect={() => setConfirming(item)}>{t("home.delete")}</DropdownMenuItem>
          </> : null}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>;
  };
  // A project's ⋯: its folder's Copy path and Reveal where the host can, then Remove from CAD, which forgets the project
  // alone (no question: nothing on disk changes, and opening the folder again brings it back).
  const removeProject = library.removeProject ? (project: LibraryProject<Model>) => {
    usage.used("home_project_remove");
    setError("");
    void current.current.removeProject?.(project).then(next => {
      setProjects(next);
      setNote(t("home.projectRemoved", { name: project.name }));
      return refresh();
    }).catch(fail);
  } : null;
  const projectMenu = (project: LibraryProject<Model>) => folderItems.length || removeProject ? <div className="cad-library-section-actions">
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-xs" aria-label={t("home.projectActionsAria", { name: project.name })}><Ellipsis aria-hidden="true" /></Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-40">
        {folderItems.map(entry => <DropdownMenuItem key={entry.action} disabled={entry.action === "reveal" && project.missing} onSelect={() => {
          usage.used(PROJECT_CONTROLS[entry.action as keyof typeof PROJECT_CONTROLS]);
          void Promise.resolve(fileActions?.perform?.[entry.action]?.({ path: project.root, kind: "directory" })).catch(fail);
        }}>{entry.label}</DropdownMenuItem>)}
        {removeProject ? <>
          {folderItems.length ? <DropdownMenuSeparator /> : null}
          <DropdownMenuItem variant="destructive" onSelect={() => removeProject(project)}>{t("home.projectRemove")}</DropdownMenuItem>
        </> : null}
      </DropdownMenuContent>
    </DropdownMenu>
  </div> : null;
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
  // One section's documents, as cards or as rows under their header.
  const documents = (list: readonly Model[], inProject: boolean) => layout === "list"
    ? <div className="cad-library-table"><Columns /><ul className="cad-library-list" aria-label={t("home.filesAria")}>{list.map(item => <li key={item.path} className="cad-library-row" data-missing={item.missing || undefined} data-opening={opening === item.path || undefined}>
      <div className="cad-library-main">
        <button type="button" className="cad-library-open" disabled={item.missing} aria-label={t("home.openAria", { name: item.name })} aria-busy={opening === item.path || undefined} onClick={() => open(item)}>
          {name(item)}
          {columns(item)}
        </button>
        {actions(item, inProject)}
      </div>
    </li>)}</ul></div>
    : <ul className="cad-library-grid" aria-label={t("home.filesAria")}>{list.map(item => <li key={item.path} className="cad-library-card" data-missing={item.missing || undefined} data-opening={opening === item.path || undefined}>
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
        {actions(item, inProject)}
      </div>
    </li>)}</ul>;
  // Each project, headed by its name, its folder and its ⋯, then its documents up to its Show all; with a search or the
  // type filter, those that match, every one, and a project with none is left out.
  const projectNodes = projectSections.map(({ project, documents: listedDocuments, matching }) => {
    if (filtering && !matching.length) return null;
    const whole = filtering || expanded.has(project.id);
    const toggle = () => {
      if (!expanded.has(project.id)) usage.used("home_project_more");
      setExpanded(previous => { const next = new Set(previous); if (!next.delete(project.id)) next.add(project.id); return next; });
    };
    return <section key={project.id} className="cad-library-section" aria-label={project.name} data-project={project.id}
      data-focus={focused === project.id || undefined} ref={element => { if (element) sections.current.set(project.id, element); else sections.current.delete(project.id); }}>
      <div className="cad-library-section-head">
        <h2 className="cad-library-section-title"><Folder className="cad-library-glyph" aria-hidden="true" /><span className="cad-library-label">{project.name}</span></h2>
        <span className="cad-library-section-path" title={project.root}>{tildePath(project.root, home)}</span>
        {projectMenu(project)}
      </div>
      {project.missing ? <p className="cad-library-section-empty">{t("home.projectMissing")}</p>
        : !listedDocuments.length ? <p className="cad-library-section-empty">{t("home.projectEmpty")}</p>
          : documents(whole ? matching : matching.slice(0, PROJECT_TILES), true)}
      {!filtering && listedDocuments.length > PROJECT_TILES ? <button type="button" className="cad-library-more" aria-expanded={whole} onClick={toggle}>
        {whole ? t("home.showFewer") : t("home.showAll", { count: listedDocuments.length })}</button> : null}
      {project.truncated && whole ? <p className="cad-library-section-empty">{t("home.projectTruncated")}</p> : null}
    </section>;
  });
  const anyProjectShown = projectNodes.some(Boolean);
  // Import, the host's chooser of a file or a folder: neutral, as every control of the row is (never a filled primary).
  const importMenu = importFile || importFolder ? <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild>
      <Button variant="outline" size="xs" className="cad-library-pick h-control gap-1.5 px-2.5 text-ui">
        <FolderOpen className="size-4" aria-hidden="true" />{t("home.import")}<ChevronDown className="size-3.5 text-muted-foreground" aria-hidden="true" /></Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="min-w-40">
      {importFile ? <DropdownMenuItem onSelect={importFile}>{t("home.importFile")}</DropdownMenuItem> : null}
      {importFolder ? <DropdownMenuItem onSelect={importFolder}>{t("home.importFolder")}</DropdownMenuItem> : null}
    </DropdownMenuContent>
  </DropdownMenu> : null;
  const heading = <h1 className="cad-library-heading" data-library-heading={slots ? "navbar" : "page"}>{t("home.title")}</h1>;
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
  // Nothing at all yet: no project, no document.
  const empty = !all.length && !projectSections.length;
  // A page: it scrolls, with the platform's own scrollbar, only when there is more of it than fits.
  return <div className="cad-library h-full overflow-y-auto text-ui" data-library-layout={layout}>
    <main className="cad-library-content" aria-label={t("home.modelsAria")}>
      {/* Home's controls: in the navbar where there is one (`slots`), else in this row, which keeps the filter and the
          layout either way, 28px, on the grid's column: the row keeps its shape from the first open to the hundredth. */}
      {slots ? <>
        {slots.left ? createPortal(heading, slots.left) : null}
        {slots.right ? createPortal(<>{search}{importMenu}</>, slots.right) : null}
      </> : null}
      <div className="cad-library-toolbar" data-library-toolbar={slots ? "filters" : "page"}>
        {slots ? (kindMenu ?? <span />) : heading}
        <div className="cad-library-controls">
          {slots ? null : kindMenu}
          {slots ? null : search}
          {layoutSwitch}
          {slots ? null : importMenu}
        </div>
      </div>
      {error ? <div className="cad-library-error" role="alert"><p>{error}</p></div> : null}
      {note ? <p className="cad-library-note" role="status">{note}</p> : null}
      {items === null ? <Placeholders layout={layout} />
        : filtering && !empty && !shown.length && !anyProjectShown ? <p className="cad-library-empty" role="status">{t("home.noMatchingModels")}</p>
          : empty ? <div className="cad-library-welcome" data-library-empty="">
            <span className="cad-library-welcome-stage"><img src={logo} alt="" draggable={false} /></span>
            <h2 className="cad-library-welcome-title">{t("home.emptyTitle")}</h2>
            <p className="cad-library-welcome-body">{t("home.emptyBody")}</p>
            {importFile || importFolder ? <div className="cad-library-welcome-actions">
              {importFile ? <Button variant="outline" size="xs" className="cad-library-pick h-control gap-1.5 px-2.5 text-ui" onClick={importFile}>
                <FolderOpen className="size-4" aria-hidden="true" />{t("home.importFileButton")}</Button> : null}
              {importFolder ? <Button variant="outline" size="xs" className="cad-library-pick h-control gap-1.5 px-2.5 text-ui" onClick={importFolder}>
                <Folder className="size-4" aria-hidden="true" />{t("home.importFolderButton")}</Button> : null}
            </div> : null}
            <p className="cad-library-welcome-formats" aria-hidden="true">{WELCOME_FORMATS}</p>
          </div>
            : <>
              {projectNodes}
              {shown.length ? <section className="cad-library-section" aria-label={t("home.standalone")} data-standalone="">
                {projectSections.length ? <div className="cad-library-section-head">
                  <h2 className="cad-library-section-title"><span className="cad-library-label">{t("home.standalone")}</span></h2>
                </div> : null}
                {documents(shown, false)}
              </section> : null}
            </>}
      {confirm}
    </main>
  </div>;
}
