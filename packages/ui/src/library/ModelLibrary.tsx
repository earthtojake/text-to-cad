import { Fragment, useCallback, useEffect, useId, useLayoutEffect, useMemo, useRef, useState, type ChangeEvent, type ComponentType, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { ArrowDownUp, ArrowLeft, ChevronDown, Clock, Ellipsis, Folder, FolderOpen, LayoutGrid, List, Search, Star } from "lucide-react";
import { Badge } from "../primitives/badge.jsx";
import { Button } from "../primitives/button.jsx";
import { VALUE_DROPDOWN_LIST_CLASS } from "../primitives/value-dropdown.jsx";
import { SegmentedControl } from "../primitives/segmented-control.jsx";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuSub, DropdownMenuSubContent,
  DropdownMenuSubTrigger, DropdownMenuTrigger } from "../primitives/dropdown-menu.jsx";
import { Input } from "../primitives/input.jsx";
import { Kbd } from "../primitives/kbd.jsx";
import { Spinner } from "../primitives/spinner.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { TREE_GLYPH_STROKE } from "../primitives/tree-row.jsx";
import { documentKind } from "@cad/core/lib/fileFormats.js";
import { useI18n } from "../i18n/index.js";
import type { LibraryLayout, LibrarySort } from "../tab-store/tabRecord.js";
import { DocumentGlyph } from "../file-viewer/navigation/DocumentGlyph.jsx";
import { entryMenu, fileOpenMenu, fileOpener, openInMenu } from "../file-viewer/navigation/entry-menu.js";
import type { EntryAction, OpenInEntry } from "../file-viewer/navigation/index.js";
import { OpenInItems, useOpenInApps } from "../file-viewer/navigation/OpenInItems.jsx";
import { PANEL_ROW_VARIABLES } from "../file-viewer/panelToggles.js";
import type { FileActions, OpenInFiles } from "../file-viewer/types.js";
import type { HomeLocation, NavigationTarget, ViewerHost } from "../host/types.js";
import { documentTarget, folderPlace as projectFolder } from "../host/addresses.js";
import { useControlUsage } from "../usage/controls.js";
import { useNavbarSlots } from "../file-viewer/navbarSlots.js";
import { activityLabel, ageLabel, lastActivity } from "../lib/age.js";
import { NAVBAR_CONTROL_CLASS, NAVBAR_ROW_CLASS } from "../lib/navbarRow.js";
import { hasOpenPopup, ownsEscape } from "../lib/popups.js";
import { cn } from "../lib/utils.js";
import { PlaceLink, plainClick } from "./LibraryPlaces.jsx";
import { LibraryFrame } from "./LibrarySidebar.jsx";
import { PICTURE_CLASS, ROW_PICTURE_CLASS } from "./thumbnails.js";
import logo from "../assets/logo-c.svg";

/**
 * A file the host lists: a document (a CAD file a page opens) in its library or in a project's folder, or, in a folder
 * alone, a file that is none (`documentKind: null`: a PDF, a script, another tool's native file).
 */
export interface LibraryModel {
  /** The file, by its absolute path. */
  path: string;
  /** Its document's id, where the host names one: its picture is read by it, and its page is named by it. */
  id?: string;
  /** The file's name. */
  name: string;
  /** The folder it is in, absolute. */
  folder: string;
  /** When a page last opened it, in seconds; null for one no page has opened. */
  opened: number | null;
  /** When the file last changed, in seconds. */
  updated: number | null;
  /** When the library first knew it, in seconds; null for a file of a project's folder it does not know. */
  created: number | null;
  /**
   * Starred: kept in the home's Starred place. The page says "starred" and "Star", as Figma, Drive and Dropbox do; the
   * library, its rows, the host's `change` actions (`pin`, `unpin`) and the place's address (`pinned`) keep the word
   * they shipped with.
   */
  pinned: boolean;
  /** Gone from where it was: listed, but not openable. */
  missing: boolean;
  /** Its picture's token, which changes with the picture: `thumbnail()` reads it. Null: no picture of the file as it is now. */
  thumbnail: string | null;
  /** When the picture was taken, in seconds; null without one. */
  pictured: number | null;
  /**
   * How many part occurrences its document holds, where the host knows it for the file as it is now; null or absent
   * where it does not. A model's badge reads it: one is a Part, more an Assembly.
   */
  parts?: number | null;
  /** The id of the nearest project above it (`LibraryProject`); none for a document in no project. */
  project?: string | null;
  /**
   * Its document's type, where the host names it: `cad.registry`'s spelling (`model`, `step`, `3mf`, `kicad_pcb`...).
   * A row without it is known by its file's extension. Null: the host says
   * the file is no document (`isDocument`): it has no page, picture or pin, and is opened in an app of the computer's.
   */
  documentKind?: string | null;
}

/** Whether a row is a document, a file a page opens: every row but one its host says is none (`documentKind: null`). */
export const isDocument = (item: Pick<LibraryModel, "documentKind">) => item.documentKind !== null;

/** A folder a person opened as a project, as the host lists it (a CAD host's `CadProject`). */
export interface LibraryProject {
  id: string;
  /** Its folder's name. */
  name: string;
  /** Its folder, `/`-separated. */
  root: string;
  /** When it was last opened as a project, in seconds. */
  opened: number | null;
  /** Its folder is gone: listed, until the person removes it. */
  missing: boolean;
}

/** A folder of a project, below its root (`path`, `/`-separated; `""` the root), as the host lists it. */
export interface LibraryFolderRef { name: string; path: string }
/**
 * One folder of a project as the host reads it (a CAD host's `CadProjectFolder`): its subfolders, in the folder's
 * order, then every file in it, documents and the files no page opens together; or, asked with words, every file below
 * it that holds them, and no folders. `truncated`: not all of it is listed.
 */
export interface LibraryFolder<Model extends LibraryModel = LibraryModel> {
  project: LibraryProject;
  path: string;
  folders: readonly LibraryFolderRef[];
  documents: readonly Model[];
  truncated: boolean;
}

/** What came of Import's Folder: the project the folder chosen is, whether it was made now, and that folder. */
export interface ImportedProject {
  project: { id: string; name: string; root: string };
  /** False: the folder was a project already, or is inside the one answered. */
  made: boolean;
  /** The folder the person chose, `/`-separated. */
  folder: string;
}
/** What came of Import's one chooser of either (`importAny`): a file, which the host has shown, or a folder opened as a project. */
export type ImportedFileOrProject = { file: string } | ImportedProject;

// A file's format as people name it, by its extension; one not here is its extension, upper case. An xbf is not here:
// it is the engine's own document saved as a file, what a model's page shows, so it is a model (`isModel`), named as
// desktop CAD names its own documents (`ModelLabels`).
const FORMATS: Readonly<Record<string, string>> = { step: "STEP", stp: "STEP", stl: "STL", glb: "GLB", gltf: "GLTF", "3mf": "3MF",
  dxf: "DXF", urdf: "URDF", kicad_pcb: "KiCad PCB", kicad_sch: "KiCad SCH" };
/** The formats the viewer opens, under the welcome: names, not language. */
const WELCOME_FORMATS = ["STEP", "STL", "3MF", "GLB", "DXF", "KiCad", "URDF"].join(" · ");
const extensionOf = (path: string) => {
  const name = path.split(/[\\/]/).pop() ?? "";
  return name.includes(".") ? name.slice(name.lastIndexOf(".") + 1).toLowerCase() : "";
};
/**
 * Whether a row is a model: an `.xbf`, the engine's own document saved as a file (the same thing a model's page shows),
 * by its type where the host names it, else by its extension. Only its label: an xbf is a file, kept as one.
 */
const isModel = (item: LibraryModel) => documentKind(item.documentKind) === "xbf" || extensionOf(item.path) === "xbf";
/**
 * What a model (`isModel`) is called, as desktop CAD calls its own documents: a `part` when its document holds one part
 * occurrence, an `assembly` when it holds more, and where the host does not know how many (`parts`) its format, `xbf`
 * ("XBF", a format's name in every language): never a guess.
 */
export interface ModelLabels { xbf: string; part: string; assembly: string }
/**
 * What a card's badge and a row's Type say: a model's `labels` (`ModelLabels`), else a file's format ("STEP", "KiCad
 * PCB"); a file that is no document, its extension as its name writes it, upper case ("PDF", "PY"), and nothing with none.
 */
export function formatLabel(item: LibraryModel, labels: ModelLabels): string {
  if (isModel(item)) {
    const parts = item.parts;
    return typeof parts !== "number" || !Number.isInteger(parts) || parts < 1 ? labels.xbf : parts === 1 ? labels.part : labels.assembly;
  }
  const extension = extensionOf(item.path);
  return FORMATS[extension] ?? extension.toUpperCase();
}

/** A host's library of documents: read, changed and opened through the host. */
export interface ModelLibrarySource<Model extends LibraryModel = LibraryModel> {
  /** Starred first, then by last activity (`lastActivity`), newest first. */
  list(): Promise<readonly Model[]>;
  /** Star (`pin`) or unstar (`unpin`) a document: starred, it is kept; nothing on disk changes. The list as it now is. */
  change(action: "pin" | "unpin", model: Model): Promise<readonly Model[]>;
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
  /** The projects, the latest activity first. A host with none lists none. */
  projects?(): Promise<readonly LibraryProject[]>;
  /**
   * One folder of a project (`path`, below its root; the root with none), or with words (`q`) every file anywhere
   * below it whose path below it holds them all. A project's page is read through it.
   */
  folder?(project: string, options: { path?: string; q?: string }): Promise<LibraryFolder<Model>>;
  /**
   * Import's Folder: a folder chosen with the desktop's chooser -- opening in `start` where one is named -- opened as
   * a project; null when the person cancels. A host on a computer with no chooser has none.
   */
  importFolder?(start?: string): Promise<ImportedProject | null>;
  /**
   * Import with the desktop's one chooser of a file or a folder, where its computer has one (a Mac's open panel, as
   * VS Code's "Open…" is there): a file chosen is shown, as `pick` shows one (`{ file }`, its path), and a folder
   * opened as a project, answered as `importFolder` answers; null when the person cancels. Where a host has it, the
   * home's Import is one button opening it, and its welcome's too; elsewhere Import is File… and Folder…. Windows' and
   * Linux's choosers take one or the other, so a host there has none.
   */
  importAny?(): Promise<ImportedFileOrProject | null>;
  /** Remove from CAD: the project forgotten, nothing in its folder. The projects as they now are. */
  removeProject?(project: LibraryProject): Promise<readonly LibraryProject[]>;
}

/** The home with no place named: every document opened lately. */
export const RECENTS: HomeLocation = Object.freeze({ view: "recents" });
/** A place's name as the page says it. */
const PLACE_NAMES = Object.freeze({ recents: "home.place.recents", pinned: "home.place.starred" } as const);
/** A place as one word: what marks its row in the sidebar (a project's, whichever of its folders is on screen). */
export const placeKey = (place: HomeLocation) => (place.view === "project" ? `project:${place.project}` : place.view);
/** The folder of a project's page, below its root: `""` its root. */
const folderOf = (place: HomeLocation) => (place.view === "project" ? place.path ?? "" : "");
/** Whether two places are one: the same place, and on a project's page the same folder. */
export const samePlace = (a: HomeLocation, b: HomeLocation) => placeKey(a) === placeKey(b) && folderOf(a) === folderOf(b);

/**
 * A place's documents in the order the person chose, each by what the list shows: by last activity (the later of when a
 * page last opened it and when it last changed, which is what a card's line says), newest first; by name; by when a page
 * last opened it, newest first; or by when it last changed, newest first. A file with no such time comes last. The
 * host's order where two tie. A starred document is not first: Starred is a place of its own.
 */
export function sortDocuments<Model extends LibraryModel>(documents: readonly Model[], sort: LibrarySort, locale?: string): Model[] {
  const names = new Intl.Collator(locale, { numeric: true, sensitivity: "base" });
  const time = (value: number | null | undefined) => typeof value === "number" && Number.isFinite(value) ? value : 0;
  const by = (a: Model, b: Model) => sort === "name" ? names.compare(a.name, b.name)
    : sort === "viewed" ? time(b.opened) - time(a.opened)
      : sort === "edited" ? time(b.updated) - time(a.updated)
        : time(lastActivity(b)) - time(lastActivity(a));
  return documents.map((item, index) => ({ item, index })).sort((a, b) => by(a.item, b.item) || a.index - b.index).map(({ item }) => item);
}

const slashed = (path: string) => path.replace(/\\/g, "/").replace(/\/+$/, "");
/** `path` under `root`, `/`-separated: "" for the folder itself, and the path as it is where it is not under it. */
export function below(path: string, root: string): string {
  const shown = slashed(path), base = slashed(root);
  return shown === base ? "" : base && shown.startsWith(`${base}/`) ? shown.slice(base.length + 1) : shown;
}

/** `path` below `root`, `/`-separated, where it is strictly below it; null for the folder itself and for any other. */
const strictlyBelow = (path: string, root: string): string | null => {
  const shown = slashed(path), base = slashed(root);
  return base && shown.startsWith(`${base}/`) ? shown.slice(base.length + 1) : null;
};

/**
 * The files a project's top page leads with (`docs/viewer-ux.md`, "The home"): the library's rows (`items`, what
 * Recents lists: opened by someone, or built by a run) of `project` that are not in its top folder but below it, by
 * last activity, newest first. Read from the library alone, never from a folder.
 */
export function recentBelow<Model extends LibraryModel>(items: readonly Model[], project: Pick<LibraryProject, "id" | "root">, locale?: string): Model[] {
  return sortDocuments(items.filter(item => item.project === project.id && strictlyBelow(item.folder ?? "", project.root)), "activity", locale);
}

/**
 * How many columns a grid (`element`) draws now, as the browser resolved its tracks: a grid of `auto-fill` columns
 * lists every one, filled or not. Measured again whenever its box changes size, so a resize changes the count with no
 * reload. One where it is not laid out.
 */
function useColumns(element: HTMLElement | null): number {
  const [count, setCount] = useState(1);
  useLayoutEffect(() => {
    if (!element) return undefined;
    const measure = () => setCount(Math.max(1, getComputedStyle(element).gridTemplateColumns.split(" ").filter(track => track && track !== "none").length));
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  return count;
}

/** Whether every word of `query` is in its name or its path (below `root` where one is given: the project's folder is no part of what was typed). */
const matches = (item: LibraryModel, words: readonly string[], root?: string) => {
  const text = `${item.name}\n${root ? below(item.path, root) : item.path}`.toLowerCase();
  return words.every(word => text.includes(word));
};
const wordsOf = (query: string) => query.trim().toLowerCase().split(/\s+/).filter(Boolean);

export function filterModels<Model extends LibraryModel>(items: readonly Model[], query: string, root?: string): Model[] {
  const words = wordsOf(query);
  return items.filter(item => matches(item, words, root));
}

const message = (failure: unknown) => failure instanceof Error ? failure.message : String(failure);
/** How often the home reads its list (and a project's page its folder) again while it is up. */
const LIST_MS = 2_000;
/** How long typing rests before a project's page asks its host to search below the folder on screen. */
const SEARCH_WAIT_MS = 150;
/** The orders a place's documents can be in, as Sort's menu lists them. */
const SORTS: readonly LibrarySort[] = ["activity", "name", "viewed", "edited"];
/** The most rows a project's top page's Recent shows in the list; in the grid, its one row holds what fits across. */
const RECENT_ROWS = 5;

// A card's or a row's picture (`thumbnails.ts`'s one picture), read once it is on screen: the one its row names, else its
// kind's glyph. A card's is its full width and carries its format's badge (`badge`: the system's chip, 8px in from the
// picture's corner); a row's (`row`) is the search's row picture.
function Picture<Model extends LibraryModel>({ item, load, opening = false, badge = null, row = false }: {
  item: Model; load(item: Model): Promise<string | null>; opening?: boolean; badge?: string | null; row?: boolean }) {
  const { t } = useI18n();
  const element = useRef<HTMLSpanElement>(null);
  const [image, setImage] = useState<string | null>(null);
  const latest = useRef(item);
  latest.current = item;
  useEffect(() => {
    let active = true;
    // A new picture replaces the old one once it has loaded, never through the placeholder.
    if (!item.thumbnail || item.missing) { setImage(null); return undefined; }
    if (!element.current) return undefined;
    const show = () => { void load(latest.current).then(value => { if (active) setImage(value); }).catch(() => {}); };
    if (typeof IntersectionObserver === "undefined") { show(); return () => { active = false; }; }
    const observer = new IntersectionObserver(entries => {
      if (!entries.some(entry => entry.isIntersecting)) return;
      observer.disconnect();
      show();
    });
    observer.observe(element.current);
    return () => { active = false; observer.disconnect(); };
  }, [item.path, item.thumbnail, item.missing, load]);
  return <span className={cn(row ? ROW_PICTURE_CLASS : cn(PICTURE_CLASS, "w-full border-b border-border"), "group-data-missing/entry:opacity-50")} data-library-picture="" ref={element}>
    {image ? <img src={image} alt="" className={cn("absolute inset-0 size-full object-contain", row && "p-0.5")} draggable={false} />
      : <DocumentGlyph path={item.path} className="size-glyph" strokeWidth={TREE_GLYPH_STROKE} />}
    {badge ? <Badge variant="secondary" className="absolute top-2 left-2 h-chip border-border font-medium" aria-hidden="true" data-library-format="">{badge}</Badge> : null}
    {opening ? <span className="absolute inset-0 grid place-items-center bg-background/50 text-foreground" data-library-opening="">
      <Spinner className="size-glyph" aria-label={t("home.openingAria", { name: item.name })} /></span> : null}
  </span>;
}

// The list: a header of muted labels the control tall over rows the control + 16 tall (the search's row, as tall as its
// picture needs), each its picture and name, then what a card says in columns of fixed widths, 16px apart: its type (the
// card's badge), when a page last opened it and when it last changed. A row's fill hangs 8px past the place's line, so
// the header's labels, the pictures and the folders' glyphs stand on the line; its two actions float over its right end,
// in the room its padding keeps. A narrower place drops Type, then Last viewed.
const COLUMNS_CLASS = `flex min-w-0 items-center gap-4`;
const NAME_COLUMN_CLASS = "flex min-w-0 flex-[3_1_0] items-center gap-2";
const COLUMN_CLASS: Readonly<Record<string, string>> = {
  type: "w-24 flex-none truncate @max-[560px]:hidden", viewed: "w-28 flex-none truncate @max-[440px]:hidden", edited: "w-28 flex-none truncate",
};
const COLUMN_NAMES = ["type", "viewed", "edited"] as const;

/** The list's header row: Name, Type, Last viewed, Last edited, over the columns its rows draw (a label each, for the eye: a row names itself). */
function Columns() {
  const { t } = useI18n();
  return <div className={cn(COLUMNS_CLASS, "h-control pr-[calc(var(--cad-icon-button)*2+8px)] text-muted-foreground select-none")} aria-hidden="true" data-library-columns="">
    <span className={cn(NAME_COLUMN_CLASS, "truncate")}>{t("home.columnName")}</span>
    {COLUMN_NAMES.map(column => <span key={column} className={COLUMN_CLASS[column]} data-column={column}>
      {t(`home.column${column[0].toUpperCase()}${column.slice(1)}`)}</span>)}
  </div>;
}

// A card: one box on the card's colour with a card's corners, the picture edge to edge over its caption, padded by a
// card's inset. A row: the search's row, its fill the row's (`primitives/tree-row.jsx`).
const GRID_CLASS = "m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(200px,1fr))] items-start gap-4 p-0";
const LIST_CLASS = "-mx-2 my-0 flex list-none flex-col p-0";
const CARD_OPEN_CLASS = "cad-library-open flex w-full min-w-0 cursor-pointer flex-col text-left text-inherit no-underline outline-none disabled:cursor-default";
const CARD_CLASS = "cad-library-card group/entry relative min-w-0 scroll-m-4 overflow-hidden rounded-lg border border-border bg-card transition-colors";
const ROW_CLASS = "cad-library-row group/entry relative min-w-0 scroll-m-4";
// A row's press: under the pointer the row's fill (`bg-accent/50`); in keyboard focus, or being opened, a selected row's
// (`bg-brand-subtle`) with the chrome's ring; the document just left, ringed 2px in the brand.
const ROW_OPEN_CLASS = cn("cad-library-open w-full cursor-pointer rounded-md px-2 text-left text-inherit no-underline outline-none transition-colors disabled:cursor-default", COLUMNS_CLASS,
  "h-[calc(var(--cad-control)+16px)] pr-[calc(var(--cad-icon-button)*2+16px)] not-disabled:hover:bg-accent/50",
  "focus-visible:bg-brand-subtle focus-visible:ring-2 focus-visible:ring-ring/45 focus-visible:ring-inset group-data-opening/entry:bg-brand-subtle",
  "group-data-from/entry:ring-2 group-data-from/entry:ring-brand group-data-from/entry:ring-inset");
const CAPTION_CLASS = "flex min-w-0 flex-col p-3 group-data-missing/entry:opacity-50";
// A label over a block of a place (a project's top page's Recent and All files): the body's size, medium, in the foreground.
const SECTION_LABEL_CLASS = "m-0 font-medium text-foreground";
// A folder among the cards: a card's box (its own name, so a card is still a file's), a card's inset all round its glyph
// and its name, so its name stands where a card's does.
const FOLDER_TILE_CLASS = CARD_CLASS.replace("cad-library-card", "cad-library-folder");
const FOLDER_OPEN_CLASS = "cad-library-open flex w-full min-w-0 cursor-pointer items-center gap-2 p-3 text-left text-inherit no-underline outline-none";
// A file the viewer does not open, among the cards: the folder's tile (its own name), its ⋯ in a square at its right
// end as tall as the tile's inside (its line and its insets), centred there, so the button is padded alike on every side
// and its glyph ends 16px in on both scales; the name ends where that square starts.
const FILE_TILE_CLASS = CARD_CLASS.replace("cad-library-card", "cad-library-file");
const FILE_OPEN_CLASS = cn(FOLDER_OPEN_CLASS, "pr-[calc(var(--cad-leading-ui)+24px)] disabled:cursor-default");
const FILE_ACTIONS_CLASS = "absolute inset-y-0 right-0 grid w-[calc(var(--cad-leading-ui)+24px)] place-items-center";
/** A placeholder's bar on the line its text will stand on (`TreeRowsLoading`'s bar). */
const bar = (line: string, width: string) => <span className={cn("flex items-center", line)}><span className={cn("block h-2 rounded-full bg-muted-foreground/20", width)} /></span>;

/** Where the models will be while the list is read: cards (or rows, under their header) in their own places, pulsing. */
function Placeholders({ layout }: { layout: LibraryLayout }) {
  const { t } = useI18n();
  const status = <li className="sr-only" role="status">{t("home.loadingFiles")}</li>;
  return layout === "list"
    ? <div className="cad-library-table"><Columns /><ul className={cn(LIST_CLASS, "motion-safe:animate-pulse")} aria-label={t("home.filesAria")} aria-busy="true" data-loading="">{status}{[0, 1, 2].map(index =>
      <li key={index} className={ROW_CLASS} aria-hidden="true"><span className={ROW_OPEN_CLASS}>
        <span className={NAME_COLUMN_CLASS}><span className={ROW_PICTURE_CLASS} />{bar("h-(--cad-leading-ui) flex-1", "w-2/5")}</span></span>
      </li>)}</ul></div>
    : <ul className={cn(GRID_CLASS, "motion-safe:animate-pulse")} aria-label={t("home.filesAria")} aria-busy="true" data-loading="">{status}{[0, 1, 2, 3].map(index =>
      <li key={index} className={CARD_CLASS} aria-hidden="true"><span className={CARD_OPEN_CLASS}>
        <span className={cn(PICTURE_CLASS, "w-full border-b border-border")} />
        <span className={CAPTION_CLASS}>{bar("h-(--cad-leading-ui)", "w-3/5")}{bar("h-(--cad-leading-ui)", "w-1/3")}</span>
      </span></li>)}</ul>;
}

/**
 * A card's, a row's or a place's press target: a real link where it has an address (`href`), so the browser's own ways
 * of opening one in a new tab work on it (⌘ or Ctrl and a click, a middle click, the link's menu) and a plain click is
 * `onPress`, in this view; a button where it has none, or cannot be opened (`disabled`).
 */
function PressTarget({ href = null, disabled = false, onPress, children, ...props }: {
  href?: string | null; disabled?: boolean; onPress(): void; children: ReactNode; className?: string;
  "aria-label"?: string; "aria-busy"?: boolean; "data-library-crumb"?: string; "data-library-file"?: string;
}) {
  if (href && !disabled) return <a href={href} onClick={event => { if (!plainClick(event)) return; event.preventDefault(); onPress(); }} {...props}>{children}</a>;
  return <button type="button" disabled={disabled} onClick={onPress} {...props}>{children}</button>;
}

/** A file as the host's actions name it: its path, and its id where the host listed one (a folder's file has no other name). */
const fileEntry = (item: LibraryModel) => ({ path: item.path, kind: "file" as const, ...(item.id ? { id: item.id } : {}) });
const NO_PLACES: ReadonlySet<EntryAction> = new Set();

/**
 * A card's or a row's ⋯: one menu for every file. What leads it is the caller's (`lead`: a document's Open and Open in
 * new tab), then Open in, a submenu of the apps the host lists for the file and Default app (`OpenInItems`, the rows the
 * navbar's Open in draws), looked up as the menu opens and there only once the host has listed something; then what
 * the host can do with a file on disk (`items`: Copy path, Copy link, the file manager); then the caller's last item
 * (`tail`: a document's Star or Unstar). Nothing at all where there would be no item.
 */
function FileMenu<Model extends LibraryModel>({ item, fileActions, items, lead = null, tail = null, label, className, variant, onPerform, onFail }: {
  item: Model; fileActions?: FileActions; items: readonly { action: EntryAction; label: string }[]; lead?: ReactNode; tail?: ReactNode; label: string;
  className?: string; variant: "ghost" | "outline"; onPerform(action: EntryAction, item: Model): void; onFail(failure: unknown): void }) {
  const { t } = useI18n();
  const usage = useControlUsage();
  const [open, setOpen] = useState(false);
  const asks = fileActions?.apps, opens = fileActions?.openApp;
  const file = useMemo(() => fileEntry(item), [item.path, item.id]);
  const apps = useMemo(() => (asks && opens && !item.missing ? (options: { signal: AbortSignal }) => asks(file, options) : null), [asks, opens, file, item.missing]);
  const files = useOpenInApps(open, apps) as OpenInFiles | null;
  if (!lead && !tail && !apps && !items.length) return null;
  const platform = fileActions?.platform ?? "linux";
  const entries = !files ? [] : isDocument(item) ? openInMenu(platform, NO_PLACES, t, { files }) : fileOpenMenu(platform, NO_PLACES, t, { files });
  const choose = (entry: OpenInEntry) => { usage.used("file_open_app"); void Promise.resolve(opens?.(file, entry.target ?? "", entry.app ?? "")).catch(onFail); };
  const openIn = t("file.openIn");
  return <DropdownMenu modal={false} open={open} onOpenChange={setOpen}>
    <DropdownMenuTrigger asChild>
      <Button variant={variant} size="icon-xs" className={className} aria-label={label}><Ellipsis aria-hidden="true" /></Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="min-w-40">
      {lead}
      {entries.length ? <DropdownMenuSub>
        <DropdownMenuSubTrigger data-open-in-menu="">{openIn}</DropdownMenuSubTrigger>
        <DropdownMenuSubContent aria-label={openIn}><OpenInItems entries={entries} onChoose={choose} /></DropdownMenuSubContent>
      </DropdownMenuSub> : null}
      {items.map(entry => <DropdownMenuItem key={entry.action} onSelect={() => onPerform(entry.action, item)}>{entry.label}</DropdownMenuItem>)}
      {tail}
    </DropdownMenuContent>
  </DropdownMenu>;
}

/** Escape's key, as a keyboard prints it: a key's name, the same in every language. */
const ESCAPE_KEY = "Esc";
// A small icon button that opens a menu (a card's, a row's and a project's ⋯): muted, on the accent fill while it is open.
const MENU_BUTTON_CLASS = "text-muted-foreground data-[state=open]:bg-accent data-[state=open]:text-foreground";
// A card's and a row's star and ⋯: there under the pointer or the keyboard, while its menu is open, always where nothing
// hovers, and the star always while it is on.
const ACTION_CLASS = "opacity-0 transition-opacity group-hover/entry:opacity-100 group-focus-within/entry:opacity-100 data-[state=open]:opacity-100 "
  + "aria-pressed:opacity-100 [@media(hover:none)]:opacity-100 motion-reduce:transition-none";
/** What the home keeps of its sidebar (`LibrarySidebar.jsx`): the person's choice of open or closed, and its width. */
export interface LibraryPanel { open?: boolean; width?: number }
/** One place of the home as its row draws it: its glyph and its name, and no count, as Figma's and Drive's sidebars have none. */
interface PlaceRow { place: HomeLocation; key: string; label: string; Icon: ComponentType<any>; missing?: boolean }
/** What the home asks of the host's navigation: a target's address, and a target opened beside this view. */
export type LibraryNavigation = Pick<ViewerHost["navigation"], "hrefOf" | "openBeside">;
/** The document the person just left for a project's page: its card is ringed, and Back and Escape return to it. */
export interface LibraryOrigin {
  /** The file's absolute path: the row's `path`. */
  path: string;
  /** Its document's id, where the host knows it: the row's `id`. */
  id?: string | null;
  name: string;
}
/** A folder's read on a project's page: the folder and the words it was asked with, and what came of it. */
interface FolderRead<Model extends LibraryModel> { at: string; words: string; folder: LibraryFolder<Model> | null; failed: boolean }

/**
 * The host's home: every document the viewer knows, one place at a time, to open again. The viewer's navbar is over it
 * (the logo, the sidebar's toggle, the host's update and Full size, as over a file), holding at its right end the
 * search and, where the host has a chooser, Import (one button where one chooser takes a file or a folder, a Mac's:
 * `importAny`; else its File and its Folder); with no navbar they stand in a bar of the page's own. Neither names the
 * home: the place's title says where the person is, and the logo is the way home. The
 * page is on the page's colour (`--background`), full width. It is drawn as Figma's and Drive's file browsers are:
 * three sizes (a title, one body size told apart by weight and colour, and a chip's step), places with no counts,
 * a card's line its activity alone, and no list of "files in no folder".
 *
 * At its left, a sidebar of places (`LibrarySidebar.jsx`), which is the viewer's panel over this page: pinned it pushes
 * the place, collapsed it leaves nothing but a peek from its toggle, a phone's is a sheet, its width the person's by its
 * grip (232px at first), and what the person chose of it is kept (`panel`, `onPanelChange`). It ends in the panel's
 * foot (the host's links and Settings), as a document's panel does. Its places: Recents (`place`'s
 * default: every document opened lately, across projects, as `library.list()` gives them; a document in no project is
 * found there and by the search), Starred, then "Projects" with a "+" (Import's Folder, where the host has a chooser)
 * over one row a project (`projects()`: its folder glyph and name, the latest activity first; one whose folder is gone
 * muted). Its rows are the panel's (`primitives/tree-row.jsx`), with no count, the one on screen marked (`aria-current`),
 * Up and Down moving between them; each is a link where the host gives places an address (`navigation.hrefOf`).
 *
 * The main area shows the place on screen, under one row. At its left is the title, the page's `h1`: the place's
 * name; on a project's page, the folder glyph and the folder's path, the project's name first and each part a way
 * back up to it (the last, the folder on screen, the title), and its ⋯ (Open in new tab, Copy path, Reveal, then
 * Remove from CAD, which forgets the project and nothing on disk). At its right end, the way back, then, wherever the
 * place lists anything, Sort (Last activity, Name, Last viewed, Last edited: one ghost button and its menu) and grid or
 * list (one segmented control), centred on the title. The title is the first to truncate; where the row is narrow Sort
 * is its glyph alone. There is no filter by kind.
 *
 * A project's page is one folder of it (`library.folder`, read again every `LIST_MS`): its subfolders first, each its
 * glyph and its name and a way into it, then every file directly in it, the documents, then the files no page opens
 * (`isDocument`: in the grid each a tile of the folders' family after the cards, having no picture to show; in the list
 * a row after the documents'; opened in an app of the computer's by a press, `openFile`, with Open in in its ⋯ and no
 * star), each group in the Sort's order. At the project's top, the files of it opened or built lately
 * below the top (`recentBelow`, the library's rows) lead, labelled Recent: one row of the cards' grid, as many as fit
 * across, or five rows of the list; the listing follows, labelled All files. Recents and Starred are the library's
 * rows. Each document is
 * a card (a picture badged with its format -- for an `.xbf` file "Part" or "Assembly", by its `parts`, "XBF" (its
 * format) where that is not known -- over the name and its last activity with its verb; no glyph) or a row (Name, Type: its format as the badge says it, a folder's "Folder"; Last viewed; Last edited). A card's picture is
 * the one its row names, else its format's tile: the home draws none. A card's or a row's main press is a link where
 * the host gives the document an address (it is named by its `id`; a row with none by its `path`), a button
 * otherwise. Each has a star and one ⋯ menu (`FileMenu`): Open, Open in new tab (or Open in browser:
 * `navigation.openBeside`), Open in (the host's apps for its files, looked up as the menu opens), Copy path, Copy link
 * and Reveal where the host can, then Star or Unstar. Nothing on the home deletes a file or forgets one.
 *
 * The search narrows the place on screen: Recents and Starred by the rows in hand; a project's page asks the host for
 * every file below the folder on screen (`library.folder` with `q`), the one place its levels are flattened.
 *
 * The place is padded by the panel's inset (16px) on every side, at every width and on a phone: its heading, its
 * folders' glyphs and its cards stand on that one line.
 *
 * `from` (the document the navbar's project name was pressed over) rings that document's card in the brand's colour,
 * brought into view, and puts "Back to <name>" at the title row's right end; Escape, while no menu, dialog or field has
 * the keyboard, goes back too (`onBack`).
 *
 * Nothing waits unseen. While the list is read, placeholder cards (or rows) stand where the documents will be, and
 * placeholder rows where the projects will be. A document being opened shows a spinner over its picture, and the
 * library takes no other open until the host has opened it or failed to.
 */
export function ModelLibrary<Model extends LibraryModel>({ library, layout = "grid", onLayoutChange, sort = "activity", onSortChange, fileActions,
  place: placed, onPlaceChange, onPlaceShown, from = null, onBack, navigation, panel = null, onPanelChange }: {
  library: ModelLibrarySource<Model>;
  /** What the host can do with a file on disk (Copy path, Reveal): each file's menu offers it, and each project's. */
  fileActions?: FileActions;
  /** Grid or list; the host keeps the choice (the tab's settings). */
  layout?: LibraryLayout;
  onLayoutChange?(layout: LibraryLayout): void;
  /** The order of the place's documents; the host keeps the choice with the layout. Without `onSortChange` there is no Sort. */
  sort?: LibrarySort;
  onSortChange?(sort: LibrarySort): void;
  /** The place on screen, where the host keeps it (its address, its history); without it the home keeps its own, from Recents. */
  place?: HomeLocation;
  /** The person chose a place: a row of the sidebar, a folder, Import's Folder (the project it opened), Remove from CAD (Recents). */
  onPlaceChange?(place: HomeLocation): void;
  /** The place on screen by its name, as the person reads it ("Recents", a project's folder's name): what a host titles its page with. */
  onPlaceShown?(name: string): void;
  /** The document the person just left for this place: ringed, with the way back to it. */
  from?: LibraryOrigin | null;
  onBack?(): void;
  /** The host's addresses and its Open in new tab (`ViewerHost.navigation`): links for buttons, and the menus' item. */
  navigation?: LibraryNavigation;
  /** The sidebar as the person left it, where the host keeps it (the tab's settings); without it the home keeps its own while it is up. */
  panel?: LibraryPanel | null;
  /** The person opened or closed the sidebar, or dragged its width: the whole of what is kept. */
  onPanelChange?(panel: LibraryPanel): void;
}) {
  const [items, setItems] = useState<readonly Model[] | null>(null);
  const [projects, setProjects] = useState<readonly LibraryProject[] | null>(null);
  // The projects could not be read, and none are shown: said where they would be.
  const [projectsFailed, setProjectsFailed] = useState(false);
  const [query, setQueryState] = useState("");
  // What a person does on the home, counted (`usage/controls.js`): a search begun, never what it looks for.
  const usage = useControlUsage();
  const setQuery = (next: string) => { if (!query.trim() && next.trim()) usage.used("home_search"); setQueryState(next); };
  const [error, setError] = useState("");
  const { t, locale } = useI18n();
  // The place on screen: the host's (`placed`), else the home's own.
  const [ownPlace, setOwnPlace] = useState<HomeLocation>(RECENTS);
  const place = placed ?? ownPlace;
  const here = placeKey(place);
  // On a project's page, the folder on screen, below the project's root ("" its root), and what to read it by.
  const folderPath = folderOf(place);
  const folderAt = place.view === "project" ? JSON.stringify([place.project, folderPath]) : "";
  // What came of the last Import's Folder or Remove from CAD, in a line over the place it led to; gone with the place.
  const [note, setNote] = useState<{ text: string; at: string } | null>(null);
  const show = (next: HomeLocation) => { setOwnPlace(next); onPlaceChange?.(next); };
  // The host's library as it is now: a host may hand a new one each render.
  const current = useRef(library);
  current.current = library;
  const images = useRef(new Map<string, Promise<string | null>>());
  // The same list again is not news: the cards keep their state and are not drawn again. The projects are read with
  // it (`readProjects`); a read of them that fails keeps the ones shown.
  const readProjects = useCallback(() => (current.current.projects
    ? current.current.projects().then(found => { setProjectsFailed(false); return found; }, () => { setProjectsFailed(true); return undefined; })
    : Promise.resolve([])).then(found => {
    if (found !== undefined) setProjects(previous => previous && JSON.stringify(previous) === JSON.stringify(found) ? previous : found);
  }), []);
  const refresh = useCallback(() => Promise.all([current.current.list(), readProjects()]).then(([next]) => {
    setItems(previous => previous && JSON.stringify(previous) === JSON.stringify(next) ? previous : next);
  }), [readProjects]);
  // Read on mount, again every couple of seconds while the home is up (a model rebuilt meanwhile has its picture
  // and its count again), and when the page is shown.
  useEffect(() => {
    void refresh().catch(failure => { setItems([]); setError(message(failure)); });
    const again = () => { void refresh().catch(() => {}); };
    const timer = setInterval(again, LIST_MS);
    document.addEventListener("visibilitychange", again);
    return () => { clearInterval(timer); document.removeEventListener("visibilitychange", again); };
  }, [refresh]);
  // A project's page: its folder, read through the host as it is shown, again every couple of seconds and when the page
  // is shown; with words typed, every file below it that holds them, asked once typing rests (the last answer
  // wins). The same answer twice is not news. Until the first answer of a new search, the one before stays, narrowed
  // by the words here.
  const words = place.view === "project" ? query.trim() : "";
  const [read, setRead] = useState<FolderRead<Model> | null>(null);
  const askFolder = useRef<() => void>(() => {});
  useEffect(() => {
    const source = current.current;
    if (place.view !== "project" || !source.folder) { askFolder.current = () => {}; return undefined; }
    const project = place.project;
    let live = true;
    const ask = () => {
      void current.current.folder?.(project, { path: folderPath, ...(words ? { q: words } : {}) }).then(folder => {
        if (live) setRead(previous => previous && previous.at === folderAt && previous.words === words && !previous.failed
          && JSON.stringify(previous.folder) === JSON.stringify(folder) ? previous : { at: folderAt, words, folder, failed: false });
      }, () => {
        if (live) setRead(previous => ({ at: folderAt, words, folder: previous?.at === folderAt && previous.words === words ? previous.folder : null, failed: true }));
      });
    };
    askFolder.current = ask;
    const first = words ? setTimeout(ask, SEARCH_WAIT_MS) : null;
    if (!words) ask();
    const timer = setInterval(ask, LIST_MS);
    document.addEventListener("visibilitychange", ask);
    return () => { live = false; if (first) clearTimeout(first); clearInterval(timer); document.removeEventListener("visibilitychange", ask); };
  }, [folderAt, words]);
  const folderRead = read && read.at === folderAt ? read : null;
  const load = useCallback((item: Model) => {
    // A picture is kept by its token: a new picture of the row is another token.
    const name = `${item.id ?? item.path}\n${item.thumbnail}`;
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
  // A press on a file that is no document (`isDocument`) opens it too: there is no page for it, so it is handed to an app
  // of this computer's, chosen from the host's answer for the file as it is pressed (`fileOpener`): the OS's own handler
  // where the host offers it, else the first app it lists; where it lists neither, or the open fails, the place's line
  // says so (the host's own words where it has them), and the file's ⋯ still shows it in the file manager. A host that
  // cannot open apps shows the file in its file manager where it can do that; where it can do neither, the file has
  // no press at all (`pressable`).
  const canOpenApps = Boolean(fileActions?.apps && fileActions.openApp);
  const pressable = (item: Model) => isDocument(item) || canOpenApps || Boolean(fileActions?.perform?.reveal);
  const openFile = (item: Model) => {
    if (opening) return;
    const file = fileEntry(item);
    setError("");
    if (!canOpenApps) { usage.used("home_reveal"); void Promise.resolve(fileActions?.perform?.reveal?.(file)).catch(fail); return; }
    setOpening(item.path);
    void Promise.resolve(fileActions?.apps?.(file)).then(files => {
      const opener = fileOpener(files);
      if (!opener) throw new Error(t("home.noAppOpens", { name: item.name }));
      usage.used("file_open_app");
      return fileActions?.openApp?.(file, opener.target, opener.app);
    }).catch(fail).finally(() => setOpening(null));
  };
  // The person's own move to a place: a row of the sidebar, a folder of a project, or a part of its path.
  const PLACE_CONTROLS = { recents: "home_place_recents", pinned: "home_place_pinned", project: "home_place_project" } as const;
  const visit = (next: HomeLocation) => {
    if (samePlace(next, place)) return;
    usage.used(PLACE_CONTROLS[next.view]);
    setError("");
    show(next);
  };
  // The project Import's Folder just opened, until the projects read again list it: its page waits for it.
  const [arriving, setArriving] = useState<string | null>(null);
  // Import, at the navbar's right end: the host's chooser of a file (shown as it is chosen) or of a folder (opened as a
  // project, whose page is shown at the folder chosen, with a line saying what came of it), where its computer has one.
  const importFile = library.pick ? () => { usage.used("home_pick"); setError(""); setNote(null); void current.current.pick?.().catch(fail); } : null;
  // A folder chosen, opened as a project: that project's page, at the folder chosen where it is inside the project.
  const arrive = ({ project, made, folder }: ImportedProject) => {
    const inside = below(folder, project.root);
    const next = projectFolder(project.id, inside && inside !== slashed(folder) ? inside : "");
    setArriving(project.id);
    setNote({ at: placeKey(next), text: made ? t("home.projectMade", { name: project.name })
      : !inside ? t("home.projectAgain", { name: project.name })
        : t("home.projectInside", { name: folder.split("/").filter(Boolean).pop() ?? folder, project: project.name }) });
    show(next);
    return refresh();
  };
  const importFolder = library.importFolder ? () => {
    usage.used("home_import_folder");
    setError("");
    setNote(null);
    void current.current.importFolder?.().then(imported => (imported ? arrive(imported) : undefined)).catch(fail);
  } : null;
  // Import with the one chooser of a file or a folder, where the host's computer has one (a Mac's): a file is shown by
  // the host, as File's is, and a folder opened as a project, as Folder's is. Counted by what was chosen, by the names
  // File and Folder are counted by; a chooser cancelled counts nothing.
  const importAny = library.importAny ? () => {
    setError("");
    setNote(null);
    void current.current.importAny?.().then(imported => {
      if (!imported) return undefined;
      if ("file" in imported) { usage.used("home_pick"); return undefined; }
      usage.used("home_import_folder");
      return arrive(imported);
    }).catch(fail);
  } : null;
  // A change answers the library as it now is; a project's page, whose rows say whether each is starred, reads its folder again.
  const change = (action: "pin" | "unpin", item: Model) => current.current.change(action, item)
    .then(next => { setItems(next); askFolder.current(); }, fail);
  const all = items ?? [];
  // Home's navbar (`file-viewer/navbarSlots.js`): the search and Import go to its right end; where there is no navbar
  // they stand in a bar of the page's own.
  const slots = useNavbarSlots();
  // A narrow navbar (under 700px: `styles/globals.css`) shows the search as its icon until it is pressed.
  const [searchOpen, setSearchOpen] = useState(false);
  // The places. Starred, from the library's rows (`pinned`); a project's page, from its folder.
  const known = new Map((projects ?? []).map(project => [project.id, project]));
  const pinned = all.filter(item => item.pinned);
  const shownProject = place.view === "project" ? known.get(place.project) ?? null : null;
  useEffect(() => { if (arriving && projects?.some(project => project.id === arriving)) setArriving(null); }, [arriving, projects]);
  // A project's page before its project is listed: one Import's Folder just opened, or the first read of the projects.
  const awaited = place.view === "project" && !shownProject && (projects === null ? !projectsFailed : arriving === place.project);
  const placeName = place.view === "project" ? shownProject?.name ?? t("home.project") : t(PLACE_NAMES[place.view]);
  // The folder on screen's path, a part a level: the project's name first, each a way back up to its folder.
  const crumbs = place.view === "project" ? [{ name: placeName, path: "" }, ...folderPath.split("/").filter(Boolean)
    .map((name, index, parts) => ({ name, path: parts.slice(0, index + 1).join("/") }))] : [];
  const shownAs = crumbs.length ? crumbs[crumbs.length - 1].name : placeName;
  const shownName = useRef(onPlaceShown);
  shownName.current = onPlaceShown;
  useEffect(() => { shownName.current?.(shownAs); }, [shownAs]);
  const labels: ModelLabels = { xbf: t("format.xbf"), part: t("home.formatPart"), assembly: t("home.formatAssembly") };
  const format = (item: Model) => formatLabel(item, labels);
  const listing = folderRead?.folder ?? null;
  // A search on a project's page: the host's answer for the words, or the one before narrowed by them here until it comes.
  const searching = place.view === "project" && Boolean(words);
  const folders = listing && !searching ? listing.folders : [];
  const inPlace = place.view === "project" ? listing?.documents ?? [] : place.view === "pinned" ? pinned : all;
  const ordered = sortDocuments(inPlace, sort, locale);
  // On a project's page by the path below its folder, as the host's answer is, so the listing narrowed meanwhile is the answer's.
  const matching = filterModels(ordered, query, shownProject?.root);
  // A project's top page leads with what was opened or built below its top folder (`recentBelow`), as Drive's Home leads
  // with its Suggested files and Box's All Files with its Recents: one row of the grid, as many cards as fit across
  // (`useColumns`), or five rows of the list, then the listing under "All files". Never on a folder below the top, and
  // never in a search, which replaces it.
  const [recentGrid, setRecentGrid] = useState<HTMLUListElement | null>(null);
  const fitAcross = useColumns(recentGrid);
  const recent = place.view === "project" && !folderPath && !searching && shownProject ? recentBelow(all, shownProject, locale) : [];
  const recentShown = recent.slice(0, layout === "list" ? RECENT_ROWS : fitAcross);
  const [recentLabel, allLabel] = [useId(), useId()];
  const now = Date.now();
  // The document just left, among the place's: its card is ringed and brought into view.
  const left = (item: Model) => Boolean(from && (slashed(item.path) === slashed(from.path) || (from.id && item.id === from.id)));
  const ringed = useRef<HTMLLIElement | null>(null);
  const leftKey = from && [...recentShown, ...matching].some(left) ? `${folderAt || here}\n${from.path}` : "";
  useEffect(() => { if (leftKey) ringed.current?.scrollIntoView?.({ block: "nearest" }); }, [leftKey]);
  // Escape goes back to the document just left, while nothing else has the key: a menu or a dialog that is up, a
  // field being typed in, or something that spends its own Escape.
  const back = from && onBack ? () => { usage.used("home_back"); onBack(); } : null;
  const goBack = useRef(back);
  goBack.current = back;
  const returning = Boolean(back);
  useEffect(() => {
    if (!returning) return undefined;
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || event.defaultPrevented || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target instanceof Element ? event.target : null;
      if (target?.closest("input, textarea, select, [contenteditable]") || ownsEscape(target)) return;
      if (hasOpenPopup(document.body) || document.querySelector("[role=dialog], [role=alertdialog], [role=menu]")) return;
      event.preventDefault();
      goBack.current?.();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [returning]);
  // What the host can do with a card's document (Copy path, Copy link, Reveal), and with a folder (Copy path, Reveal).
  const fileItems = entryMenu(fileActions?.platform ?? "linux", new Set(Object.keys(fileActions?.perform ?? {}) as EntryAction[]), t);
  const folderItems = fileItems.filter(entry => entry.action === "copy-path" || entry.action === "reveal");
  const HOME_CONTROLS = { "copy-path": "home_copy_path", "copy-link": "home_copy_link", reveal: "home_reveal" } as const;
  const PROJECT_CONTROLS = { "copy-path": "home_project_copy_path", reveal: "home_project_reveal" } as const;
  const perform = (action: EntryAction, item: Model) => {
    if (action in HOME_CONTROLS) usage.used(HOME_CONTROLS[action as keyof typeof HOME_CONTROLS]);
    void Promise.resolve(fileActions?.perform?.[action]?.({ path: item.path, kind: "file", ...(item.id ? { id: item.id } : {}) })).catch(fail);
  };
  // The host's addresses and its way to open a target beside this view. A document is named by its id (a CAD host
  // knows each file it lists by its id); a row with no id, by its path, which the host resolves as it opens it.
  const hrefOf = navigation?.hrefOf, beside = navigation?.openBeside;
  const targetOf = (item: Model): NavigationTarget => documentTarget(item);
  const besideLabel = beside ? t(beside.kind === "browser" ? "home.openBrowser" : "home.openNewTab") : "";
  const openBeside = (target: NavigationTarget, control: "home_open_new_tab" | "home_project_open_new_tab") => {
    usage.used(control);
    setError("");
    void Promise.resolve().then(() => beside?.open(target)).catch(fail);
  };
  // A card's star and its one menu (`FileMenu`: Open, Open in new tab, Open in, what the host can do with a file on disk,
  // then Star or Unstar), there while the pointer is on the card (Figma's star): the star toggles, and a starred card
  // shows it, filled in the foreground, whatever the pointer does; its hint says what a press does. A file that is no
  // document has the menu alone, with Open in and what the host can do with a file: it has no page to open and is in
  // no library to star it in. Nothing here deletes a file or forgets one, as nothing in Figma's or Drive's file browser
  // forgets a file: a file goes where the person deletes it, in their file manager. Star or Unstar, from the card's
  // star or its menu: counted alike, by the names the counts shipped with (`home_pin`, `home_unpin`).
  const star = (item: Model) => { usage.used(item.pinned ? "home_unpin" : "home_pin"); void change(item.pinned ? "unpin" : "pin", item); };
  // Where they stand: over a card's picture's corner (`card`, outline buttons on the picture's light ground), over a
  // row's right end (`row`), or centred in a file's tile's end square (`tile`).
  const ACTIONS_AT = { card: "light top-2 right-2 flex items-center gap-1", row: "top-1/2 right-2 flex -translate-y-1/2 items-center gap-1", tile: FILE_ACTIONS_CLASS } as const;
  const actions = (item: Model, at: keyof typeof ACTIONS_AT) => {
    const document = isDocument(item);
    const variant = at === "card" ? "outline" : "ghost";
    const starLabel = t(item.pinned ? "home.unstar" : "home.star");
    return <div className={cn("absolute", ACTIONS_AT[at])} data-library-actions="">
      {document ? <TooltipHint content={starLabel}>
        <Button variant={variant} size="icon-xs" className={cn(ACTION_CLASS, "text-muted-foreground aria-pressed:text-foreground")} aria-label={starLabel} aria-pressed={item.pinned}
          data-library-star="" onClick={() => star(item)}><Star aria-hidden="true" fill={item.pinned ? "currentColor" : "none"} /></Button>
      </TooltipHint> : null}
      <FileMenu item={item} fileActions={fileActions} variant={variant} className={cn(ACTION_CLASS, MENU_BUTTON_CLASS)} label={t("home.actionsAria", { name: item.name })}
        items={document ? fileItems : fileItems.filter(entry => entry.action !== "copy-link")} onPerform={perform} onFail={fail}
        lead={document ? <>
          <DropdownMenuItem disabled={item.missing} onSelect={() => open(item)}>{t("home.menuOpen")}</DropdownMenuItem>
          {beside ? <DropdownMenuItem disabled={item.missing} onSelect={() => openBeside(targetOf(item), "home_open_new_tab")}>{besideLabel}</DropdownMenuItem> : null}
        </> : null}
        tail={document ? <DropdownMenuItem onSelect={() => star(item)}>{starLabel}</DropdownMenuItem> : null} />
    </div>;
  };
  // The ⋯ of a project's page: Open in new tab first, where the host opens a place beside this view; the folder on
  // screen's Copy path and Reveal where the host can; then Remove from CAD, which forgets the project alone (no
  // question: nothing on disk changes, and opening the folder again brings it back) and goes to Recents, saying so.
  const removeProject = library.removeProject ? (project: LibraryProject) => {
    usage.used("home_project_remove");
    setError("");
    void current.current.removeProject?.(project).then(next => {
      setProjects(next);
      setNote({ at: placeKey(RECENTS), text: t("home.projectRemoved", { name: project.name }) });
      show(RECENTS);
      return refresh();
    }).catch(fail);
  } : null;
  const besidePlaces = beside && beside.places !== false;
  const folderOnScreen = shownProject ? (folderPath ? `${slashed(shownProject.root)}/${folderPath}` : shownProject.root) : "";
  const projectMenu = (project: LibraryProject) => besidePlaces || folderItems.length || removeProject ? <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-xs" className={cn("flex-none", MENU_BUTTON_CLASS)} aria-label={t("home.projectActionsAria", { name: project.name })}><Ellipsis aria-hidden="true" /></Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="min-w-40">
        {besidePlaces ? <DropdownMenuItem onSelect={() => openBeside({ home: place }, "home_project_open_new_tab")}>{besideLabel}</DropdownMenuItem> : null}
        {folderItems.map(entry => <DropdownMenuItem key={entry.action} disabled={entry.action === "reveal" && project.missing} onSelect={() => {
          usage.used(PROJECT_CONTROLS[entry.action as keyof typeof PROJECT_CONTROLS]);
          void Promise.resolve(fileActions?.perform?.[entry.action]?.({ path: folderOnScreen, kind: "directory" })).catch(fail);
        }}>{entry.label}</DropdownMenuItem>)}
        {removeProject ? <>
          {besidePlaces || folderItems.length ? <DropdownMenuSeparator /> : null}
          <DropdownMenuItem variant="destructive" onSelect={() => removeProject(project)}>{t("home.projectRemove")}</DropdownMenuItem>
        </> : null}
      </DropdownMenuContent>
    </DropdownMenu> : null;
  const age = (seconds: number | null) => ageLabel(seconds, now, t, locale);
  // A card's line: its last activity with its verb, Edited or Viewed, whichever came last, and nothing before it, as
  // Figma's cards say "Edited 2 hours ago" alone. The list says both its times.
  const status = (item: Model) => item.missing ? t("home.fileUnavailable") : activityLabel(item, now, t, locale);
  // A row's name: its picture (the search's row picture, its spinner over it while it is being opened), then its name in
  // the foreground at regular weight: a list's emphasis is colour.
  const name = (item: Model) => <span className={cn(NAME_COLUMN_CLASS, "group-data-missing/entry:opacity-50")} data-library-name="">
    <Picture item={item} load={load} opening={opening === item.path} row />
    <span className="truncate text-foreground" data-library-label="">{item.name}</span>
  </span>;
  // A row's columns, muted, what a card says: its type (the card's badge), when a page last opened it and when it last
  // changed, with no verb; a dash for what is not known. A folder's type is "Folder".
  const cell = (column: string, value: ReactNode) => <span key={column} className={cn(COLUMN_CLASS[column], "text-muted-foreground")} data-column={column}>{value === "" || value == null ? "—" : value}</span>;
  const columns = (item: Model) => <>
    {cell("type", format(item))}
    {cell("viewed", age(item.opened))}
    {cell("edited", item.missing ? t("home.fileUnavailable") : age(item.updated))}
  </>;
  // A file's entry, a card or a row (`row`): its main press, then its pin and ⋯. A document's press is a link where the
  // host gives it an address. A file that is no document has no page: its press is a button that opens it in an app
  // (`openFile`), drawn and worked as a document's is; it is never ringed, being no document to come back from.
  const entry = (item: Model, row: boolean, body: ReactNode) => {
    const document = isDocument(item);
    const from = document && left(item);
    const className = row ? ROW_OPEN_CLASS : CARD_OPEN_CLASS;
    const label = t("home.openAria", { name: item.name });
    return <li key={item.path} className={row ? ROW_CLASS : CARD_CLASS} data-missing={item.missing || undefined}
      data-opening={opening === item.path || undefined} data-from={from || undefined} ref={from ? ringed : undefined}>
      {document ? <PressTarget className={className} href={item.missing ? null : hrefOf?.(targetOf(item)) ?? null} disabled={item.missing}
        aria-label={label} aria-busy={opening === item.path || undefined} onPress={() => open(item)}>{body}</PressTarget>
        : pressable(item) ? <PressTarget className={className} aria-label={label} aria-busy={opening === item.path || undefined} onPress={() => openFile(item)} data-library-file="">{body}</PressTarget>
          : <div className={cn(className, "cursor-auto")} data-library-file="">{body}</div>}
      {actions(item, row ? "row" : "card")}
    </li>;
  };
  // A subfolder of the folder on screen: its glyph and its name, a way into it (a real link where the host gives places
  // an address), and nothing else. Among cards it is a tile of the cards' own family: a card's box, column, corner and
  // inset, its name a card's name, as tall as its one line needs. In the list it is a row of the list, its glyph on the
  // picture tile a file's picture stands on, and a dash in each column.
  const folderPlace = (folder: LibraryFolderRef): HomeLocation => projectFolder(place.view === "project" ? place.project : "", folder.path);
  const folderLink = (folder: LibraryFolderRef) => {
    const href = hrefOf?.({ home: folderPlace(folder) }) ?? null;
    return { href, label: t("home.openAria", { name: folder.name }), onPress: () => visit(folderPlace(folder)) };
  };
  const folderTile = (folder: LibraryFolderRef) => {
    const { href, label, onPress } = folderLink(folder);
    return <li key={folder.path} className={FOLDER_TILE_CLASS} data-folder="">
      <PressTarget className={FOLDER_OPEN_CLASS} href={href} aria-label={label} onPress={onPress}>
        <Folder className="size-glyph flex-none text-muted-foreground" strokeWidth={TREE_GLYPH_STROKE} aria-hidden="true" />
        <span className="truncate font-medium text-foreground" data-library-label="">{folder.name}</span>
      </PressTarget>
    </li>;
  };
  // A file the viewer does not open, in the grid: it has no picture to show in a picture's space, so it is the folders'
  // compact tile, after the cards: its kind's glyph (a picture's tile shows the same for it) and its name, a press that
  // opens it in an app (`openFile`, a button: it has no address), and its ⋯ at its right end, there as a card's are.
  // While it is being opened a spinner stands where its glyph is.
  const fileTile = (item: Model) => {
    const busy = opening === item.path;
    const body = <>
      {busy ? <Spinner className="size-glyph flex-none" aria-label={t("home.openingAria", { name: item.name })} />
        : <span className="flex flex-none text-muted-foreground"><DocumentGlyph path={item.path} className="size-glyph" strokeWidth={TREE_GLYPH_STROKE} /></span>}
      <span className="truncate font-medium text-foreground" data-library-label="">{item.name}</span>
    </>;
    return <li key={item.path} className={FILE_TILE_CLASS} data-opening={busy || undefined}>
      {pressable(item) ? <PressTarget className={FILE_OPEN_CLASS} aria-label={t("home.openAria", { name: item.name })} aria-busy={busy || undefined}
        onPress={() => openFile(item)} data-library-file="">{body}</PressTarget>
        : <div className={cn(FILE_OPEN_CLASS, "cursor-auto")} data-library-file="">{body}</div>}
      {actions(item, "tile")}
    </li>;
  };
  const folderRow = (folder: LibraryFolderRef) => {
    const { href, label, onPress } = folderLink(folder);
    return <li key={folder.path} className={ROW_CLASS} data-folder="">
      <PressTarget className={ROW_OPEN_CLASS} href={href} aria-label={label} onPress={onPress}>
        <span className={NAME_COLUMN_CLASS} data-library-name="">
          <span className={ROW_PICTURE_CLASS} data-library-folder-picture=""><Folder className="size-glyph" strokeWidth={TREE_GLYPH_STROKE} aria-hidden="true" /></span>
          <span className="truncate text-foreground" data-library-label="">{folder.name}</span>
        </span>
        {cell("type", t("home.folderType"))}
        {cell("viewed", "")}
        {cell("edited", "")}
      </PressTarget>
    </li>;
  };
  // A document's card: its picture, badged, over its caption, the name, a card's title, over its one line. No glyph:
  // the picture and its badge say what it is.
  const card = (item: Model) => entry(item, false, <>
    <Picture item={item} load={load} opening={opening === item.path} badge={format(item) || null} />
    <span className={CAPTION_CLASS}>
      <span className="truncate font-medium text-foreground" data-library-label="">{item.name}</span>
      <span className="truncate text-muted-foreground" data-library-status="">{status(item)}</span>
    </span>
  </>);
  // The place's folders and files, the folders first, then the documents, then the files the viewer does not open
  // (`others`), each group in the Sort's order: in the list, rows under their header; in the grid, the folders' tiles,
  // the documents' cards, then those files' tiles, each a grid of the cards' columns, 16px apart (Drive's folders over
  // its files). A search's results are grouped alike.
  const listRow = (item: Model) => entry(item, true, <>{name(item)}{columns(item)}</>);
  const documents = (list: readonly Model[], others: readonly Model[]) => layout === "list"
    ? <div className="cad-library-table"><Columns /><ul className={LIST_CLASS} aria-label={t("home.filesAria")}>
      {folders.map(folderRow)}
      {list.map(listRow)}
      {others.map(listRow)}</ul></div>
    : <>
      {folders.length ? <ul className={GRID_CLASS} aria-label={t("home.foldersAria")} data-library-folders="">
        {folders.map(folderTile)}</ul> : null}
      {list.length ? <ul className={GRID_CLASS} aria-label={t("home.filesAria")}>{list.map(card)}</ul> : null}
      {others.length ? <ul className={GRID_CLASS} aria-label={t("home.otherFilesAria")} data-library-other-files="">{others.map(fileTile)}</ul> : null}
    </>;
  // A project's top page's Recent (`recentShown`): one row of cards in the cards' columns, or rows of the list under a
  // header of their own, the same columns.
  const recentList = layout === "list"
    ? <div className="cad-library-table"><Columns /><ul className={LIST_CLASS} aria-labelledby={recentLabel}>{recentShown.map(listRow)}</ul></div>
    : <ul ref={setRecentGrid} className={GRID_CLASS} aria-labelledby={recentLabel}>{recentShown.map(card)}</ul>;
  // Import, the host's chooser of a file or a folder: the scale's outline button, neutral as every control of the row is
  // (never a filled primary). Where one chooser takes either (`importAny`: a Mac's, as VS Code's "Open…" is there) it
  // is that button alone, opening it; elsewhere a menu of its two choosers, File… and Folder…, its chevron a dropdown's.
  const importLabel = <><FolderOpen aria-hidden="true" /><span>{t("home.import")}</span></>;
  const importMenu = importAny ? <Button variant="outline" size="control" className="cad-library-pick" aria-label={t("home.import")} onClick={importAny}>{importLabel}</Button>
    : importFile || importFolder ? <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="control" className="cad-library-pick" aria-label={t("home.import")}>
          {importLabel}<ChevronDown className="size-3 opacity-60" aria-hidden="true" /></Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-40">
        {importFile ? <DropdownMenuItem onSelect={importFile}>{t("home.importFile")}</DropdownMenuItem> : null}
        {importFolder ? <DropdownMenuItem onSelect={importFolder}>{t("home.importFolder")}</DropdownMenuItem> : null}
      </DropdownMenuContent>
    </DropdownMenu> : null;
  // The places, as the sidebar's rows list them (`LibraryPlaces.jsx`): Recents, Starred, then each project.
  const fixed = (view: "recents" | "pinned", Icon: PlaceRow["Icon"]): PlaceRow => ({ place: { view }, key: view, label: t(PLACE_NAMES[view]), Icon });
  const places = {
    lead: [fixed("recents", Clock), fixed("pinned", Star)],
    projects: (projects ?? []).map((project): PlaceRow => ({ place: { view: "project", project: project.id },
      key: placeKey({ view: "project", project: project.id }), label: project.name, Icon: Folder, missing: project.missing })),
    current: here, onVisit: visit, onAddProject: importFolder,
    loading: projects === null && !projectsFailed,
    note: projects === null ? (projectsFailed ? t("home.projectsFailed") : null) : projects.length ? null : t("home.projectsEmpty"),
    hrefOf: hrefOf ? (target: HomeLocation) => hrefOf({ home: target }) : null,
  };
  // Sort: one control, the scale's ghost button (`Button size="control"`): its sort glyph, muted, the sort's name in the
  // foreground and a dropdown's chevron, muted, padded alike from its edges to its first and last ink (the control's
  // padding), on the hover and open fill of every ghost control. No label beside it, whose box the button's fill ran
  // into: the glyph says what it is, and its accessible name says it whole ("Sort by Last activity"). Its menu is a value
  // dropdown's list (`VALUE_DROPDOWN_LIST_CLASS`): the four sorts, the chosen one ticked. Where the place is narrow
  // (a phone's) it is the glyph alone: the name and the chevron give way, the accessible name and the menu stay.
  // How the head fits its row, measured from what is drawn (`data-library-fit`'s unwrapped copies of the way back and of
  // the path's parts, which cost no room): the way back shows its glyph alone where its name would leave the title less
  // than ten heading-sized characters, and a path too wide for what the title has folds its earliest folders into one
  // "…" crumb, as few as make it fit. Neither is ever cut mid-word.
  const headRef = useRef<HTMLDivElement>(null);
  const [fit, setFit] = useState({ compact: false, folded: 0 });
  useLayoutEffect(() => {
    const head = headRef.current;
    if (!head) return;
    const measure = () => {
      const sizer = head.querySelector<HTMLElement>("[data-library-fit]");
      const headWidth = head.clientWidth;
      if (!sizer || !headWidth) return;
      const gap = parseFloat(getComputedStyle(head).columnGap) || 0;
      const own = [...head.children].filter(child => child !== sizer);
      const title = own.find(child => child.matches("[data-library-crumbs], [data-library-title]")) as HTMLElement | undefined;
      const fixed = own.filter(child => child !== title && !child.matches("[data-library-back]"));
      const used = fixed.reduce((sum, child) => sum + child.getBoundingClientRect().width, 0);
      const backFull = sizer.querySelector<HTMLElement>("[data-fit=back]");
      const count = fixed.length + 1 + (backFull ? 1 : 0);
      const heading = parseFloat(getComputedStyle(title ?? head).fontSize) || 16;
      const compact = Boolean(backFull) && headWidth - used - gap * (count - 1) - backFull!.offsetWidth < heading * 10;
      const room = headWidth - used - gap * (count - 1) - (backFull ? (compact ? backFull.offsetHeight : backFull.offsetWidth) : 0);
      const parts = [...sizer.querySelectorAll<HTMLElement>("[data-fit=crumb]")].map(part => part.offsetWidth);
      const [more, sep, last] = ["more", "sep", "last"].map(name => sizer.querySelector<HTMLElement>(`[data-fit=${name}]`)?.offsetWidth ?? 0);
      const between = parseFloat(getComputedStyle(sizer.querySelector("[data-fit-crumbs]") ?? sizer).columnGap) || 0;
      let folded = 0;
      const width = (from: number) => (from ? more + sep + between * 2 : 0) + parts.slice(from).reduce((sum, part) => sum + part + sep + between * 2, 0) + last;
      while (folded < parts.length && width(folded) > room) folded++;
      setFit(now => now.compact === compact && now.folded === folded ? now : { compact, folded });
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(head);
    const sizer = head.querySelector("[data-library-fit]");
    if (sizer) observer.observe(sizer);
    return () => observer.disconnect();
  });
  const sortName = t(`home.sort.${sort}`);
  const sortMenu: ReactNode = onSortChange ? <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild>
      <Button variant="ghost" size="control" className="min-w-0 shrink-0 focus-visible:ring-2 focus-visible:ring-ring/45 data-[state=open]:bg-accent"
        aria-label={t("home.sortByAria", { sort: sortName })} data-library-sort="">
        <ArrowDownUp className="size-glyph text-muted-foreground" aria-hidden="true" />
        <span className="min-w-0 truncate text-foreground @max-[480px]:hidden">{sortName}</span>
        <ChevronDown className="size-3 text-muted-foreground @max-[480px]:hidden" aria-hidden="true" />
      </Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" collisionPadding={8} aria-label={t("home.sortAria")} className={VALUE_DROPDOWN_LIST_CLASS}>
      <DropdownMenuRadioGroup value={sort} onValueChange={next => {
        if (next === sort) return;
        usage.used(`home_sort_${next as LibrarySort}`);
        onSortChange(next as LibrarySort);
      }}>
        {SORTS.map(value => <DropdownMenuRadioItem key={value} value={value}><span className="min-w-0 truncate">{t(`home.sort.${value}`)}</span></DropdownMenuRadioItem>)}
      </DropdownMenuRadioGroup>
    </DropdownMenuContent>
  </DropdownMenu> : null;
  // The search: in a narrow navbar its icon alone until it is pressed (it opens with the keyboard in it), and it goes
  // back to its icon when it is left empty. A field the control tall, its glyph a control's padding in.
  const search = <div className="cad-home-search flex items-center" data-open={searchOpen || query ? "" : undefined}>
    {slots ? <Button variant="ghost" size="icon-xs" className={cn("cad-home-search-button", NAVBAR_CONTROL_CLASS)} aria-label={t("home.searchAria")} aria-expanded={false}
      onClick={event => { const box = event.currentTarget.parentElement; setSearchOpen(true); requestAnimationFrame(() => box?.querySelector("input")?.focus()); }}><Search className="size-glyph" aria-hidden="true" /></Button> : null}
    <div className="cad-library-search relative w-60">
      <Search className="pointer-events-none absolute top-1/2 left-pad size-glyph -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
      <Input className="h-control pr-pad pl-[calc(var(--cad-pad)*2+var(--cad-glyph))] text-ui" type="search" aria-label={t("home.searchAria")} placeholder={t("home.searchPlaceholder")} value={query}
        onChange={(event: ChangeEvent<HTMLInputElement>) => setQuery(event.target.value)} onBlur={() => { if (!query) setSearchOpen(false); }} />
    </div>
  </div>;
  // Grid or list: one segmented control (`primitives/segmented-control.jsx`).
  const layoutSwitch = onLayoutChange ? <SegmentedControl label={t("home.layout")} value={layout}
    options={[{ value: "grid", label: t("home.grid"), Icon: LayoutGrid }, { value: "list", label: t("home.list"), Icon: List }]}
    onChange={value => { usage.used(`home_layout_${value as LibraryLayout}`); onLayoutChange(value as LibraryLayout); }} /> : null;
  // The way back to the document just left: the scale's outline button at the title row's right end, and the key that
  // does the same after it (left out where nothing hovers: a finger has no Escape). Where the row lacks room for its
  // name (a phone's) it is the back arrow alone, the one the navbar's Back draws, a control wide: a name cut mid-word
  // reads as broken, and its accessible name ("Back to <name>") and its press stay. Sort gives up its name alike.
  const backName = from ? t("home.backTo", { name: from.name }) : "";
  const backLabel = <><span className="truncate">{backName}</span><Kbd className="[@media(hover:none)]:hidden" aria-hidden="true">{ESCAPE_KEY}</Kbd></>;
  const backControl = back && from ? fit.compact
    ? <Button variant="outline" size="control" className="ml-auto w-control flex-none px-0" aria-label={backName} aria-keyshortcuts="Escape" onClick={back} data-library-back="" data-compact="">
      <ArrowLeft aria-hidden="true" /></Button>
    : <Button variant="outline" size="control" className="ml-auto flex-none" aria-keyshortcuts="Escape" onClick={back} data-library-back="">{backLabel}</Button> : null;
  // The page's title, its `h1` (the navbar names no place: the logo is the way home), the one text a step over the body,
  // at medium weight (the heading step's own weight is semibold), as Figma's file browser titles a place: the place's
  // name; on a project's page, the folder's path, every part at the title's size, as Drive's and Dropbox's paths are:
  // each part but the last a way back up to its folder, regular and muted, the first to give way (down to its first
  // letters, the last keeping six characters of its own), the slashes regular and muted, the last the folder on screen, medium in the foreground.
  const TITLE_CLASS = "m-0 min-w-[6ch] truncate text-heading font-medium text-foreground";
  const CRUMB_CLASS = "rounded-control text-heading font-normal text-muted-foreground no-underline outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/45 focus-visible:ring-inset";
  const ancestors = crumbs.slice(0, -1);
  const folded = Math.min(fit.folded, ancestors.length);
  const goTo = (crumb: { path: string }) => visit(place.view === "project" ? projectFolder(place.project, crumb.path) : place);
  const slash = <span className="flex-none text-heading font-normal text-muted-foreground" aria-hidden="true">/</span>;
  const title = crumbs.length > 1 ? <div className="flex min-w-0 flex-initial items-baseline gap-1 overflow-hidden" data-library-crumbs="">
    {folded ? <>
      <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <button type="button" className={cn(CRUMB_CLASS, "flex-none px-1 data-[state=open]:text-foreground")} aria-label={t("home.parentFoldersAria")} data-library-crumb-more="">…</button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="start" collisionPadding={8} aria-label={t("home.parentFoldersAria")} className="min-w-40">
          {ancestors.slice(0, folded).map(crumb => <DropdownMenuItem key={crumb.path} onSelect={() => goTo(crumb)} data-library-crumb-item="">
            <span className="min-w-0 truncate">{crumb.name}</span></DropdownMenuItem>)}
        </DropdownMenuContent>
      </DropdownMenu>
      {slash}
    </> : null}
    {ancestors.slice(folded).map(crumb => <Fragment key={crumb.path}>
      <PressTarget className={cn(CRUMB_CLASS, "max-w-[16em] min-w-[2ch] flex-[0_1000_auto] truncate")}
        href={hrefOf?.({ home: projectFolder(shownProject?.id ?? "", crumb.path) }) ?? null} data-library-crumb=""
        onPress={() => goTo(crumb)}>{crumb.name}</PressTarget>
      {slash}
    </Fragment>)}
    <h1 className={cn(TITLE_CLASS, "flex-initial")} data-library-title="">{shownAs}</h1>
  </div> : <h1 className={TITLE_CLASS} data-library-title="">{placeName}</h1>;
  // The head's unwrapped copies, drawn at their whole width and never seen, that `fit` measures.
  const sizer = <div className="pointer-events-none invisible absolute inset-x-0 top-0 h-0 overflow-hidden" aria-hidden="true" inert data-library-fit="">
    <div className="flex w-max flex-col items-start">
    {back && from ? <Button variant="outline" size="control" className="flex-none" tabIndex={-1} data-fit="back">{backLabel}</Button> : null}
    {crumbs.length > 1 ? <div className="flex w-max items-baseline gap-1 text-heading font-normal" data-fit-crumbs="">
      <span className="flex-none px-1 font-normal" data-fit="more">…</span><span className="flex-none font-normal" data-fit="sep">/</span>
      {ancestors.map(crumb => <span key={crumb.path} className="max-w-[16em] flex-none truncate font-normal" data-fit="crumb">{crumb.name}</span>)}
      <span className="flex-none font-medium" data-fit="last">{shownAs}</span>
    </div> : null}
    </div>
  </div>;
  // Nothing at all yet: no project, no document.
  const empty = !all.length && !(projects ?? []).length;
  // The place with nothing to list says why, in a line.
  const nothing = place.view === "project" ? t("home.projectEmpty") : place.view === "pinned" ? t("home.starredEmpty") : t("home.recentsEmpty");
  // Nothing at all yet: the C mark, two controls tall, the welcome's title (the body's size at medium weight: the title's
  // size is the page's title's alone), one muted line 4px under it, then 16px apart the ways in (Import, where one
  // chooser takes either; else Import file and Import folder) and the formats the viewer opens, muted; a column centred
  // in the place.
  const welcome = <div className="flex flex-col items-center gap-4 p-4 text-center" data-library-empty="">
    <img src={logo} alt="" draggable={false} className="block size-[calc(var(--cad-control)*2)] select-none" />
    <div className="flex flex-col gap-1">
      <h2 className="m-0 font-medium text-foreground">{t("home.emptyTitle")}</h2>
      <p className="m-0 text-muted-foreground">{t("home.emptyBody")}</p>
    </div>
    {importAny ? <Button variant="outline" size="control" onClick={importAny}>{importLabel}</Button>
      : importFile || importFolder ? <div className="flex flex-wrap justify-center gap-2">
        {importFile ? <Button variant="outline" size="control" onClick={importFile}><FolderOpen aria-hidden="true" />{t("home.importFileButton")}</Button> : null}
        {importFolder ? <Button variant="outline" size="control" onClick={importFolder}><Folder aria-hidden="true" />{t("home.importFolderButton")}</Button> : null}
      </div> : null}
    <p className="m-0 text-muted-foreground" aria-hidden="true">{WELCOME_FORMATS}</p>
  </div>;
  // A place with nothing to list, or nothing that matches, says so in one muted line, where its first row would stand.
  const line = (state: string, text: string, status = false) => <p className="m-0 text-muted-foreground" role={status ? "status" : undefined} data-library-state={state}>{text}</p>;
  const reading = place.view === "project" ? !listing && !folderRead?.failed && Boolean(library.folder) : items === null;
  // The listing: the folders and the files, and under a folder listed only in part a line saying so.
  const listed = <>
    {documents(matching.filter(item => isDocument(item)), matching.filter(item => !isDocument(item)))}
    {listing?.truncated ? <p className="m-0 text-muted-foreground" data-library-truncated="">{t("home.projectTruncated")}</p> : null}
  </>;
  const body = items === null || awaited ? <Placeholders layout={layout} />
    : place.view === "project" && !shownProject ? line("gone", projectsFailed ? t("home.projectsFailed") : t("home.projectGone"))
      : shownProject?.missing ? line("missing", t("home.projectMissing"))
        : reading ? <Placeholders layout={layout} />
          : place.view === "project" && !listing && folderRead?.failed ? line("failed", t("home.folderFailed"))
            : empty && place.view === "recents" ? welcome
              : !inPlace.length && !folders.length ? line("empty", searching ? t("home.noMatchingModels") : nothing)
                : !matching.length && !folders.length ? line("unmatched", t("home.noMatchingModels"), true)
                  : recentShown.length ? <>
                    {/* Two blocks 16px apart, each under its label 8px over it (the body's size, medium, in the
                        foreground): Recent's one row, then the listing as it is without it. */}
                    <section className="grid min-w-0 grid-cols-1 gap-2" aria-labelledby={recentLabel} data-library-recent="">
                      <h2 className={SECTION_LABEL_CLASS} id={recentLabel}>{t("home.recent")}</h2>
                      {recentList}
                    </section>
                    <section className="grid min-w-0 grid-cols-1 gap-2" aria-labelledby={allLabel} data-library-all="">
                      <h2 className={SECTION_LABEL_CLASS} id={allLabel}>{t("home.allFiles")}</h2>
                      <div className="grid min-w-0 grid-cols-1 gap-4">{listed}</div>
                    </section>
                  </> : listed;
  // Whether the place lists anything, or will: its Sort and layout stand in the head then, and over
  // a search on a project's page that finds nothing, never over a line that says the place has nothing to list.
  const lists = items === null || awaited ? true
    : place.view === "project" && !shownProject ? false
      : shownProject?.missing ? false
        : reading ? true
          : place.view === "project" && !listing && folderRead?.failed ? false
            : empty && place.view === "recents" ? false
              : inPlace.length > 0 || folders.length > 0 || searching;
  return <div className="cad-library flex size-full flex-col bg-background text-ui" data-library-layout={layout} data-library-place={here}>
    {/* Home's own controls: in the navbar's right end where there is a navbar (`slots`), else in a bar of the page's own,
        the navbar's row on the panel's inset. Neither names the place: its title does. */}
    {slots ? slots.right ? createPortal(<>{search}{importMenu}</>, slots.right) : null
      : <div className={cn(NAVBAR_ROW_CLASS, "justify-end border-border bg-sidebar px-(--panel-inset)")} data-library-bar=""><div className="flex items-center gap-2">{search}{importMenu}</div></div>}
    <LibraryFrame places={places} panel={panel} onPanelChange={onPanelChange}>
      {/* A page: it scrolls, with the platform's own scrollbar, only when there is more of it than fits. Padded by the
          panel's inset on every side (more below, clear of a host's composer floating over the bottom), its blocks 16px
          apart; its rows hang past that line as the panel's do (`PANEL_ROW_VARIABLES`). */}
      <main className="@container grid min-w-0 flex-1 auto-rows-max grid-cols-1 content-start gap-4 overflow-y-auto p-(--panel-inset) pb-[calc(var(--cad-host-bottom-inset,0px)+var(--panel-inset))]"
        aria-label={t("home.modelsAria")} style={PANEL_ROW_VARIABLES as React.CSSProperties} data-library-content="">
        {/* One row, the control tall, as Figma's file browser heads a place, every control the scale's: the place's title (a
            project's folder's path, with its glyph and its ⋯) at the left, the title the first to truncate; at the right,
            where the place lists anything, the way back, Sort and the layout, centred on the title. The content starts
            16px under it. */}
        <div ref={headRef} className="relative flex min-h-control min-w-0 items-center gap-2" data-library-head="">
          {sizer}
          {shownProject ? <Folder className="size-glyph flex-none text-muted-foreground" aria-hidden="true" /> : null}
          {title}
          {shownProject ? projectMenu(shownProject) : null}
          {backControl}
          {lists ? <div className={cn("flex flex-none items-center gap-2", !backControl && "ml-auto")} data-library-toolbar="">{sortMenu}{layoutSwitch}</div> : null}
        </div>
        {error ? <p className="m-0 text-destructive" role="alert" data-library-error="">{error}</p> : null}
        {note && note.at === here ? <p className="m-0 text-foreground" role="status" data-library-note="">{note.text}</p> : null}
        {body}
      </main>
    </LibraryFrame>
  </div>;
}
