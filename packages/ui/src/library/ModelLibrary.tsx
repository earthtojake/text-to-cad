import { Fragment, useCallback, useEffect, useMemo, useRef, useState, type ChangeEvent, type ComponentType, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { ChevronDown, Clock, Ellipsis, Files, Folder, FolderOpen, LayoutGrid, List, Pin, Search } from "lucide-react";
import { Badge } from "../primitives/badge.jsx";
import { Button } from "../primitives/button.jsx";
import { ValueDropdown } from "../primitives/value-dropdown.jsx";
import { Pill, PillGroup } from "../primitives/pill.jsx";
import { SegmentedControl } from "../primitives/segmented-control.jsx";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuSub, DropdownMenuSubContent, DropdownMenuSubTrigger, DropdownMenuTrigger } from "../primitives/dropdown-menu.jsx";
import { FieldLabel } from "../primitives/field-label.jsx";
import { Input } from "../primitives/input.jsx";
import { Kbd } from "../primitives/kbd.jsx";
import { Spinner } from "../primitives/spinner.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { TREE_GLYPH_STROKE } from "../primitives/tree-row.jsx";
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
  pinned: boolean;
  /** Gone from where it was: listed, but not openable. */
  missing: boolean;
  /** Its picture's token, which changes with the picture: `thumbnail()` reads it. Null: no picture of the file as it is now. */
  thumbnail: string | null;
  /** When the picture was taken, in seconds; null without one. */
  pictured: number | null;
  /** The file's size on disk, in bytes. */
  size?: number | null;
  /**
   * How many part occurrences its document holds, where the host knows it for the file as it is now; null or absent
   * where it does not. A model's badge reads it: one is a Part, more an Assembly.
   */
  parts?: number | null;
  /** The id of the nearest project above it (`LibraryProject`); none, a standalone document's. */
  project?: string | null;
  /**
   * Its document's type, where the host names it: `cad.registry`'s spelling (`model`, `step`, `3mf`, `kicad_pcb`...).
   * The home's kinds read it (`documentKind`); a row without it is known by its file's extension. Null: the host says
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
const isModel = (item: LibraryModel) => String(item.documentKind ?? "").toLowerCase() === "model" || extensionOf(item.path) === "xbf";
/**
 * What a model (`isModel`) is called, as desktop CAD calls its own documents: a `part` when its document holds one part
 * occurrence, an `assembly` when it holds more, and where the host does not know how many (`parts`) its format, `xbf`
 * ("XBF", a format's name in every language): never a guess.
 */
export interface ModelLabels { xbf: string; part: string; assembly: string }
/**
 * What a card's badge and a row's Kind say: a model's `labels` (`ModelLabels`), else a file's format ("STEP", "KiCad
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

/**
 * What a document is, as a person names it: the home's kinds, each a chip, in this order. Not how it was made: a model
 * built from code and the STEP, STL or GLB exported from it are all 3D models.
 */
export const DOCUMENT_KINDS = ["models", "drawings", "boards", "schematics", "robots"] as const;
export type DocumentKind = (typeof DOCUMENT_KINDS)[number];
// Each document type (`cad.registry`: its `wire` spelling, which a row's `documentKind` is) and each extension the
// viewer opens, by its kind. A type the registry adds lands here, or `ModelLibrary.test.tsx` says which is missing.
const KINDS: Readonly<Record<string, DocumentKind>> = {
  model: "models", xbf: "models", step: "models", stp: "models", stl: "models", "3mf": "models", glb: "models", gltf: "models",
  dxf: "drawings", kicad_pcb: "boards", kicad_sch: "schematics", urdf: "robots", srdf: "robots",
};
/** A document's kind: by its type where the row names it, else by its file's extension; null for neither. */
export function documentKind(item: LibraryModel): DocumentKind | null {
  return KINDS[String(item.documentKind ?? "").toLowerCase()] ?? KINDS[extensionOf(item.path)] ?? null;
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

/** A host's library of documents: read, changed and opened through the host. */
export interface ModelLibrarySource<Model extends LibraryModel = LibraryModel> {
  /** Pinned first, then by last activity (`lastActivity`), newest first. */
  list(): Promise<readonly Model[]>;
  /** Pin or unpin a document (pinned, it is kept), or remove it from the lists; nothing on disk changes. The list as it now is. */
  change(action: "pin" | "unpin" | "remove", model: Model): Promise<readonly Model[]>;
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
  /** Remove from CAD: the project forgotten, nothing in its folder. The projects as they now are. */
  removeProject?(project: LibraryProject): Promise<readonly LibraryProject[]>;
}

/** The home with no place named: every document opened lately. */
export const RECENTS: HomeLocation = Object.freeze({ view: "recents" });
/** A place as one word: what marks its row in the sidebar (a project's, whichever of its folders is on screen). */
export const placeKey = (place: HomeLocation) => (place.view === "project" ? `project:${place.project}` : place.view);
/** The folder of a project's page, below its root: `""` its root. */
const folderOf = (place: HomeLocation) => (place.view === "project" ? place.path ?? "" : "");
/** Whether two places are one: the same place, and on a project's page the same folder. */
export const samePlace = (a: HomeLocation, b: HomeLocation) => placeKey(a) === placeKey(b) && folderOf(a) === folderOf(b);

const NO_LABELS: ModelLabels = Object.freeze({ xbf: "", part: "", assembly: "" });
/**
 * A place's documents in the order the person chose: by last activity (when each was last opened or changed), newest
 * first; by name; or by kind, in the kinds' order (`DOCUMENT_KINDS`, one of none last), then the models (`isModel`),
 * then by format (`format`: a model's Part, Assembly or XBF, a file's format), then by name. The host's order where
 * two tie. A pinned document is not first: Pinned is a place of its own.
 */
export function sortDocuments<Model extends LibraryModel>(documents: readonly Model[], sort: LibrarySort,
  format: (item: Model) => string = item => formatLabel(item, NO_LABELS), locale?: string): Model[] {
  const names = new Intl.Collator(locale, { numeric: true, sensitivity: "base" });
  const rank = (item: Model) => { const kind = documentKind(item); return kind ? DOCUMENT_KINDS.indexOf(kind) : DOCUMENT_KINDS.length; };
  const by = (a: Model, b: Model) => sort === "name" ? names.compare(a.name, b.name)
    : sort === "kind" ? rank(a) - rank(b) || Number(isModel(b)) - Number(isModel(a)) || names.compare(format(a), format(b)) || names.compare(a.name, b.name)
      : (lastActivity(b) ?? 0) - (lastActivity(a) ?? 0);
  return documents.map((item, index) => ({ item, index })).sort((a, b) => by(a.item, b.item) || a.index - b.index).map(({ item }) => item);
}

const slashed = (path: string) => path.replace(/\\/g, "/").replace(/\/+$/, "");
/** `path` under `root`, `/`-separated: "" for the folder itself, and the path as it is where it is not under it. */
export function below(path: string, root: string): string {
  const shown = slashed(path), base = slashed(root);
  return shown === base ? "" : base && shown.startsWith(`${base}/`) ? shown.slice(base.length + 1) : shown;
}

/** `path` as the home says it: from `~` where it is in the person's home folder (`home`). */
export function tildePath(path: string, home?: string | null): string {
  const base = (home ?? "").replace(/\\/g, "/").replace(/\/+$/, "");
  const shown = path.replace(/\\/g, "/");
  if (!base) return shown;
  return shown === base ? "~" : shown.startsWith(`${base}/`) ? `~${shown.slice(base.length)}` : shown;
}

/** Whether every word of `query` is in its name or its path. */
const matches = (item: LibraryModel, words: readonly string[]) => {
  const text = `${item.name}\n${item.path}`.toLowerCase();
  return words.every(word => text.includes(word));
};
const wordsOf = (query: string) => query.trim().toLowerCase().split(/\s+/).filter(Boolean);

export function filterModels<Model extends LibraryModel>(items: readonly Model[], query: string): Model[] {
  const words = wordsOf(query);
  return items.filter(item => matches(item, words));
}

/** What the kinds' chips show: every document, or one kind. */
export type LibraryKind = "all" | DocumentKind;
const ofKind = (item: LibraryModel, kind: LibraryKind) => kind === "all" || documentKind(item) === kind;

/** The documents a search and a kind leave, in the library's order: every model is a card of its own. */
export function shownModels<Model extends LibraryModel>(items: readonly Model[], query: string, kind: LibraryKind = "all"): Model[] {
  const words = wordsOf(query);
  return items.filter(item => ofKind(item, kind) && matches(item, words));
}

/**
 * The chips over a place's documents (`items`): All, then each kind the place holds, in the kinds' order, each with how
 * many a search (`query`) leaves of it. None where the place holds one kind or none: there is nothing to tell apart.
 */
export function kindChips(items: readonly LibraryModel[], query: string): { kind: LibraryKind; count: number }[] {
  const held = DOCUMENT_KINDS.filter(kind => items.some(item => documentKind(item) === kind));
  if (held.length < 2) return [];
  const found = filterModels(items, query);
  return [{ kind: "all", count: found.length }, ...held.map(kind => ({ kind, count: found.filter(item => documentKind(item) === kind).length }))];
}

const message = (failure: unknown) => failure instanceof Error ? failure.message : String(failure);
/** How often the home reads its list (and a project's page its folder) again while it is up. */
const LIST_MS = 2_000;
/** How long typing rests before a project's page asks its host to search below the folder on screen. */
const SEARCH_WAIT_MS = 150;

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

// The list: a header of muted labels the control tall (`TreeRowHeading`'s line) over rows the control + 16 tall (the
// search's row, as tall as its picture needs), each its picture and name, then its facts in columns of fixed widths,
// 16px apart. A row's fill hangs 8px past the place's line, as a panel's row does past the inset, so the header's
// labels, the pictures and the folders' glyphs stand on the line; its two actions float over its right end, in the room
// its padding keeps. A narrower place drops Created, then Where, then Kind, then Size.
const COLUMNS_CLASS = `flex min-w-0 items-center gap-4`;
const NAME_COLUMN_CLASS = "flex min-w-0 flex-[3_1_0] items-center gap-2";
const COLUMN_CLASS: Readonly<Record<string, string>> = {
  where: "min-w-0 flex-[2_1_0] truncate @max-[680px]:hidden", kind: "w-20 flex-none truncate @max-[560px]:hidden", size: "w-18 flex-none truncate @max-[440px]:hidden",
  updated: "w-26 flex-none truncate", created: "w-26 flex-none truncate @max-[820px]:hidden",
};

/**
 * The list's header row: Name, then where each is (a search on a project's page: Where; Recents and Pinned: Project;
 * `where`), Kind, Size, Updated, Created, over the columns its rows draw (a label each, for the eye: a row names itself).
 */
function Columns({ where = null }: { where?: string | null }) {
  const { t } = useI18n();
  return <div className={cn(COLUMNS_CLASS, "h-control pr-[calc(var(--cad-icon-button)*2+8px)] text-muted-foreground select-none")} aria-hidden="true" data-library-columns="">
    <span className={cn(NAME_COLUMN_CLASS, "truncate")}>{t("home.columnName")}</span>
    {where ? <span className={COLUMN_CLASS.where} data-column="where">{where}</span> : null}
    {(["kind", "size", "updated", "created"] as const).map(column => <span key={column} className={COLUMN_CLASS[column]} data-column={column}>
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
// A folder among the cards: a card's box (its own name, so a card is still a file's), a card's inset all round its glyph
// and its name, so its name stands where a card's does.
const FOLDER_TILE_CLASS = CARD_CLASS.replace("cad-library-card", "cad-library-folder");
const FOLDER_OPEN_CLASS = "cad-library-open flex w-full min-w-0 cursor-pointer items-center gap-2 p-3 text-left text-inherit no-underline outline-none";
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
        <span className={CAPTION_CLASS}>{bar("h-(--cad-leading-ui)", "w-3/5")}{bar("h-(--cad-leading-tiny)", "w-1/3")}</span>
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
 * the host can do with a file on disk (`items`: Copy path, Copy link, the file manager); then the caller's last items
 * (`tail`: a document's Pin and Remove from Recents). Nothing at all where there would be no item.
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
// A card's and a row's pin and ⋯: there under the pointer or the keyboard, while its menu is open, always where nothing
// hovers, and the pin always while it is on.
const ACTION_CLASS = "opacity-0 transition-opacity group-hover/entry:opacity-100 group-focus-within/entry:opacity-100 data-[state=open]:opacity-100 "
  + "aria-pressed:opacity-100 [@media(hover:none)]:opacity-100 motion-reduce:transition-none";
/** What the home keeps of its sidebar (`LibrarySidebar.jsx`): the person's choice of open or closed, and its width. */
export interface LibraryPanel { open?: boolean; width?: number }
/** One place of the home as its row draws it: a project's row has no count (its folder is not walked to count it). */
interface PlaceRow { place: HomeLocation; key: string; label: string; count?: number; Icon: ComponentType<any>; missing?: boolean }
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
 * (the logo, the sidebar's toggle, the host's update and Full size, as over a file), holding "Home", the search and, where the
 * host has a chooser, Import (its File and its Folder); with no navbar they stand in a bar of the page's own. The page
 * is on the page's colour (`--background`), full width.
 *
 * At its left, a sidebar of places (`LibrarySidebar.jsx`), which is the viewer's panel over this page: pinned it pushes
 * the place, collapsed it leaves nothing but a peek from its toggle, a phone's is a sheet, its width the person's by its
 * grip (232px at first), and what the person chose of it is kept (`panel`, `onPanelChange`). It ends in the panel's
 * foot (the host's links and Settings), as a document's panel does. Its places: Recents (`place`'s
 * default: every document opened lately, across projects, as `library.list()` gives them), Pinned with its count, then
 * "Projects" with a "+" (Import's Folder, where the host has a chooser) over one row a project (`projects()`: its folder
 * glyph and name, the latest activity first; one whose folder is gone muted), then Standalone, the documents
 * in no project. Its rows are the panel's (`primitives/tree-row.jsx`), the one on screen marked (`aria-current`), Up and
 * Down moving between them; each is a link where the host gives places an address (`navigation.hrefOf`).
 *
 * The main area shows the place on screen. Its heading row: the place's name; on a project's page, the folder glyph
 * and the folder's path, the project's name first and each part a way back up to it (the last, the folder on screen,
 * the heading), at the project's top that folder from `~` (below it the heading is the path already), and its ⋯ (Open
 * in new tab, Copy path, Reveal, then Remove from CAD, which forgets the project and nothing on disk); then Sort (Last activity, Name, Kind) and grid or list, one segmented control.
 * Under it the kinds' chips (`kindChips`: All, 3D models, Drawings, Boards, Schematics, Robots, each the place holds,
 * with its count under the search), where it holds more than one.
 *
 * A project's page is one folder of it (`library.folder`, read again every `LIST_MS`): its subfolders first, each its
 * glyph and its name and a way into it (a row, `PlaceLink`), then every file directly in it, the documents and the
 * files no page opens together (`isDocument`: one of those is a card or a row like the rest, opened in an app of the
 * computer's by a press, `openFile`, with Open in in its ⋯ and no pin). Recents, Pinned and Standalone are the
 * library's rows. Each document is a card (a picture badged with its format -- for an `.xbf` file "Part" or
 * "Assembly", by its `parts`, "XBF" (its format) where that is not known -- over the name and a line: its project's
 * name in Recents and Pinned, then its last activity with its verb; no glyph or size, which the list has) or a row
 * (Name, Where or Project, Kind: its format, Size, Updated, Created). A card's picture is the one its row names, else its
 * format's tile: the home draws none. A card's or a row's main press is a link where the host gives the document an
 * address (it is named by its `id`; a row with none by its `path`), a button otherwise. Each has a pin and one ⋯ menu
 * (`FileMenu`): Open, Open in new tab (or Open in browser: `navigation.openBeside`), Open in (the host's apps for its
 * files, looked up as the menu opens), Copy path, Copy link and Reveal where the host can, Pin or Unpin, then, but on a project's page (where a file is listed for being in the folder), Remove from Recents,
 * which forgets the library's entry of it (no question: its file is untouched, and opening it again brings it back) and
 * takes the card off the list at once. Nothing on the home deletes a file.
 *
 * The search narrows the place on screen: Recents, Pinned and Standalone by the rows in hand; a project's page asks the
 * host for every file below the folder on screen (`library.folder` with `q`), the one place its levels are
 * flattened, each row saying where it is below that folder.
 *
 * The place is padded by the panel's inset (16px) on every side, at every width and on a phone: its heading, its
 * chips' words, its folders' glyphs and its cards stand on that one line.
 *
 * `from` (the document the navbar's project name was pressed over) rings that document's card in the brand's colour,
 * brought into view, and puts "Back to <name>" in the heading row; Escape, while no menu, dialog or field has the
 * keyboard, goes back too (`onBack`).
 *
 * Nothing waits unseen. While the list is read, placeholder cards (or rows) stand where the documents will be, and
 * placeholder rows where the projects will be. A document being opened shows a spinner over its picture, and the
 * library takes no other open until the host has opened it or failed to.
 */
export function ModelLibrary<Model extends LibraryModel>({ library, layout = "grid", onLayoutChange, sort = "activity", onSortChange, fileActions,
  place: placed, onPlaceChange, onPlaceShown, from = null, onBack, navigation, home = null, panel = null, onPanelChange }: {
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
  /** The person's home folder, where the host knows it: a project's folder is said from `~` in it. */
  home?: string | null;
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
  const PLACE_CONTROLS = { recents: "home_place_recents", pinned: "home_place_pinned", standalone: "home_place_standalone", project: "home_place_project" } as const;
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
  const importFolder = library.importFolder ? () => {
    usage.used("home_import_folder");
    setError("");
    setNote(null);
    void current.current.importFolder?.().then(imported => {
      if (!imported) return;
      const { project, made, folder } = imported;
      const inside = below(folder, project.root);
      const next = projectFolder(project.id, inside && inside !== slashed(folder) ? inside : "");
      setArriving(project.id);
      setNote({ at: placeKey(next), text: made ? t("home.projectMade", { name: project.name })
        : !inside ? t("home.projectAgain", { name: project.name })
          : t("home.projectInside", { name: folder.split("/").filter(Boolean).pop() ?? folder, project: project.name }) });
      show(next);
      return refresh();
    }).catch(fail);
  } : null;
  // A change answers the library as it now is; a project's page, whose rows say whether each is pinned, reads its folder again.
  const change = (action: "pin" | "unpin" | "remove", item: Model) => current.current.change(action, item)
    .then(next => { setItems(next); askFolder.current(); }, fail);
  // Remove from Recents: the library's entry of the document forgotten, its file untouched, so nothing is asked first
  // (opening the file again brings the entry back). The card leaves the list at once.
  const [gone, setGone] = useState<ReadonlySet<string>>(() => new Set());
  const remove = (item: Model) => {
    usage.used("home_delete");
    setGone(previous => new Set([...previous, item.path]));
    void change("remove", item)
      .finally(() => setGone(previous => { const next = new Set(previous); next.delete(item.path); return next; }));
  };
  const all = (items ?? []).filter(item => !gone.has(item.path));
  const [kind, setKind] = useState<LibraryKind>("all");
  // Home's navbar (`file-viewer/navbarSlots.js`): its heading, the search and Import go there; where there is no
  // navbar they stand in a bar of the page's own.
  const slots = useNavbarSlots();
  // A narrow navbar (under 700px: `styles/globals.css`) shows the search as its icon until it is pressed.
  const [searchOpen, setSearchOpen] = useState(false);
  // The places. Pinned and Standalone, from the library's rows; a project's page, from its folder.
  const known = new Map((projects ?? []).map(project => [project.id, project]));
  const inProject = (item: Model) => Boolean(item.project && known.has(item.project));
  const standalone = all.filter(item => !inProject(item));
  const pinned = all.filter(item => item.pinned);
  const shownProject = place.view === "project" ? known.get(place.project) ?? null : null;
  useEffect(() => { if (arriving && projects?.some(project => project.id === arriving)) setArriving(null); }, [arriving, projects]);
  // A project's page before its project is listed: one Import's Folder just opened, or the first read of the projects.
  const awaited = place.view === "project" && !shownProject && (projects === null ? !projectsFailed : arriving === place.project);
  const placeName = place.view === "project" ? shownProject?.name ?? t("home.project")
    : place.view === "standalone" ? t("home.standalone") : t(`home.place.${place.view}`);
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
  const inPlace = place.view === "project" ? listing?.documents ?? []
    : place.view === "pinned" ? pinned : place.view === "standalone" ? standalone : all;
  const ordered = sortDocuments(inPlace, sort, format, locale);
  // The kinds' chips: the place's kinds, counted under the search. A kind chosen in another place that this one does
  // not hold shows all of it.
  const chips = kindChips(inPlace, query);
  const shownKind = chips.some(chip => chip.kind === kind) ? kind : "all";
  const matching = shownModels(ordered, query, shownKind);
  const now = Date.now();
  // The document just left, among the place's: its card is ringed and brought into view.
  const left = (item: Model) => Boolean(from && (slashed(item.path) === slashed(from.path) || (from.id && item.id === from.id)));
  const ringed = useRef<HTMLLIElement | null>(null);
  const leftKey = from && matching.some(left) ? `${folderAt || here}\n${from.path}` : "";
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
  // A card's pin and its one menu (`FileMenu`: Open, Open in new tab, Open in, what the host can do with a file on disk,
  // Pin or Unpin, then Remove from Recents), there while the pointer is on the card (Figma's star): the pin toggles, and a
  // pinned card shows it, filled, whatever the pointer does. A file that is no document has the menu alone, with Open in
  // and what the host can do with a file: it has no page to open and is in no library to pin it in. On a project's page there is no Remove from Recents: a file is there
  // because it is in the folder. Nothing here deletes a file: that is the person's own act, in their file manager.
  // Pin or Unpin, from the card's pin or its menu: counted alike.
  const pin = (item: Model) => { usage.used(item.pinned ? "home_unpin" : "home_pin"); void change(item.pinned ? "unpin" : "pin", item); };
  const removable = place.view !== "project";
  const actions = (item: Model, row: boolean) => {
    const document = isDocument(item);
    const variant = row ? "ghost" : "outline";
    return <div className={cn("absolute flex items-center gap-1", row ? "top-1/2 right-2 -translate-y-1/2" : "light top-2 right-2")} data-library-actions="">
      {document ? <Button variant={variant} size="icon-xs" className={cn(ACTION_CLASS, "text-muted-foreground aria-pressed:text-foreground")} aria-label={t(item.pinned ? "home.unpin" : "home.pin")} aria-pressed={item.pinned}
        data-library-pin="" onClick={() => pin(item)}><Pin aria-hidden="true" fill={item.pinned ? "currentColor" : "none"} /></Button> : null}
      <FileMenu item={item} fileActions={fileActions} variant={variant} className={cn(ACTION_CLASS, MENU_BUTTON_CLASS)} label={t("home.actionsAria", { name: item.name })}
        items={document ? fileItems : fileItems.filter(entry => entry.action !== "copy-link")} onPerform={perform} onFail={fail}
        lead={document ? <>
          <DropdownMenuItem disabled={item.missing} onSelect={() => open(item)}>{t("home.menuOpen")}</DropdownMenuItem>
          {beside ? <DropdownMenuItem disabled={item.missing} onSelect={() => openBeside(targetOf(item), "home_open_new_tab")}>{besideLabel}</DropdownMenuItem> : null}
        </> : null}
        tail={document ? <>
          <DropdownMenuItem onSelect={() => pin(item)}>{t(item.pinned ? "home.unpin" : "home.pin")}</DropdownMenuItem>
          {removable ? <>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={() => remove(item)}>{t("home.removeFromRecents")}</DropdownMenuItem>
          </> : null}
        </> : null} />
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
  // Where a document is, said where it is not plain: in a search on a project's page, its folder below the folder on
  // screen; in Recents and Pinned, where projects are listed, its project's name (Standalone for one in none).
  const across = (place.view === "recents" || place.view === "pinned") && known.size > 0;
  const where = (item: Model) => searching && shownProject ? below(item.folder ?? "", folderOnScreen)
    : across ? known.get(item.project ?? "")?.name ?? t("home.standalone") : "";
  const whereColumn = searching ? t("home.columnWhere") : across ? t("home.columnProject") : null;
  // A tile's line: where it is (its project's name in Recents and Pinned, its folder in a search on a project's page),
  // then its last activity with its verb, Edited or Viewed, whichever came last. Its size is the list's column.
  const status = (item: Model) => [where(item), item.missing ? t("home.fileUnavailable") : activityLabel(item, now, t, locale)]
    .filter(Boolean).join(" · ");
  // A row's name: its picture (the search's row picture, its spinner over it while it is being opened), then its name in
  // the foreground at regular weight: a list's emphasis is colour.
  const name = (item: Model) => <span className={cn(NAME_COLUMN_CLASS, "group-data-missing/entry:opacity-50")} data-library-name="">
    <Picture item={item} load={load} opening={opening === item.path} row />
    <span className="truncate text-foreground" data-library-label="">{item.name}</span>
  </span>;
  // A row's columns, muted: where it is, its kind and size, then its two times with no verb: when it last changed, and when the library first knew it.
  const cell = (column: string, value: ReactNode) => <span key={column} className={cn(COLUMN_CLASS[column], "text-muted-foreground")} data-column={column}>{value}</span>;
  const columns = (item: Model) => <>
    {whereColumn ? cell("where", where(item)) : null}
    {cell("kind", format(item) || "—")}
    {cell("size", sizeLabel(item.size, locale) || "—")}
    {cell("updated", item.missing ? t("home.fileUnavailable") : age(item.updated))}
    {cell("created", age(item.created))}
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
      {actions(item, row)}
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
  const folderRow = (folder: LibraryFolderRef) => {
    const { href, label, onPress } = folderLink(folder);
    return <li key={folder.path} className={ROW_CLASS} data-folder="">
      <PressTarget className={ROW_OPEN_CLASS} href={href} aria-label={label} onPress={onPress}>
        <span className={NAME_COLUMN_CLASS} data-library-name="">
          <span className={ROW_PICTURE_CLASS} data-library-folder-picture=""><Folder className="size-glyph" strokeWidth={TREE_GLYPH_STROKE} aria-hidden="true" /></span>
          <span className="truncate text-foreground" data-library-label="">{folder.name}</span>
        </span>
        {whereColumn ? cell("where", "") : null}
        {["kind", "size", "updated", "created"].map(column => cell(column, "—"))}
      </PressTarget>
    </li>;
  };
  // The place's folders and files: in the list, rows under their header, the folders first; else the folders, tiles in
  // the cards' columns, over the cards.
  const documents = (list: readonly Model[]) => layout === "list"
    ? <div className="cad-library-table" data-where={whereColumn ? "" : undefined}><Columns where={whereColumn} /><ul className={LIST_CLASS} aria-label={t("home.filesAria")}>
      {folders.map(folderRow)}
      {list.map(item => entry(item, true, <>{name(item)}{columns(item)}</>))}</ul></div>
    : <>
      {folders.length ? <ul className={GRID_CLASS} aria-label={t("home.foldersAria")} data-library-folders="">
        {folders.map(folderTile)}</ul> : null}
      {list.length ? <ul className={GRID_CLASS} aria-label={t("home.filesAria")}>{list.map(item => entry(item, false, <>
        <Picture item={item} load={load} opening={opening === item.path} badge={format(item) || null} />
        {/* The caption: the name, a card's title, over its one line. No glyph: the picture and its badge say what it is. */}
        <span className={CAPTION_CLASS}>
          <span className="truncate font-medium text-foreground" data-library-label="">{item.name}</span>
          <span className="truncate text-tiny text-muted-foreground" data-library-status="">{status(item)}</span>
        </span>
      </>))}</ul> : null}
    </>;
  // Import, the host's chooser of a file or a folder: the scale's outline button, neutral as every control of the row is
  // (never a filled primary), its chevron a dropdown's.
  const importMenu = importFile || importFolder ? <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild>
      <Button variant="outline" size="control" className="cad-library-pick" aria-label={t("home.import")}>
        <FolderOpen aria-hidden="true" /><span>{t("home.import")}</span><ChevronDown className="size-3 opacity-60" aria-hidden="true" /></Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="end" className="min-w-40">
      {importFile ? <DropdownMenuItem onSelect={importFile}>{t("home.importFile")}</DropdownMenuItem> : null}
      {importFolder ? <DropdownMenuItem onSelect={importFolder}>{t("home.importFolder")}</DropdownMenuItem> : null}
    </DropdownMenuContent>
  </DropdownMenu> : null;
  // The places, as the sidebar's rows list them (`LibraryPlaces.jsx`): Recents, Pinned, each project, Standalone.
  const fixed = (view: "recents" | "pinned" | "standalone", count: number, Icon: PlaceRow["Icon"]): PlaceRow =>
    ({ place: { view }, key: view, label: view === "standalone" ? t("home.standalone") : t(`home.place.${view}`), count, Icon });
  const places = {
    lead: [fixed("recents", 0, Clock), fixed("pinned", pinned.length, Pin)],
    projects: (projects ?? []).map((project): PlaceRow => ({ place: { view: "project", project: project.id },
      key: placeKey({ view: "project", project: project.id }), label: project.name, Icon: Folder, missing: project.missing })),
    standalone: fixed("standalone", standalone.length, Files),
    current: here, onVisit: visit, onAddProject: importFolder,
    loading: projects === null && !projectsFailed,
    note: projects === null ? (projectsFailed ? t("home.projectsFailed") : null) : projects.length ? null : t("home.projectsEmpty"),
    hrefOf: hrefOf ? (target: HomeLocation) => hrefOf({ home: target }) : null,
  };
  // The page's heading: "Home", in the navbar where there is one, drawn as a file's name is there.
  const heading = <h1 className="m-0 flex h-control min-w-0 items-center whitespace-nowrap text-ui font-normal text-foreground" data-library-heading={slots ? "navbar" : "page"}>{t("home.title")}</h1>;
  // The kinds: a row of pills (`primitives/pill.jsx`) under the heading row, All then each kind the place holds, with its
  // count; one on at a time.
  const kindRow: ReactNode = chips.length ? <PillGroup label={t("home.kindsAria")} data-library-kinds="">
    {chips.map(chip => <Pill key={chip.kind} pressed={chip.kind === shownKind} count={chip.count} data-kind={chip.kind}
      aria-label={t("home.kindCount", { kind: t(`home.kind.${chip.kind}`), count: chip.count })}
      onClick={() => { if (chip.kind !== shownKind) usage.used(`home_kind_${chip.kind}`); setKind(chip.kind); }}>{t(`home.kind.${chip.kind}`)}</Pill>)}
  </PillGroup> : null;
  // Sort: a muted label and the one value dropdown (`primitives/value-dropdown.jsx`), set to fit beside it.
  const sortMenu: ReactNode = onSortChange ? <span className="flex min-w-0 items-center"><FieldLabel className="flex-none">{t("home.sortAria")}</FieldLabel>
    <ValueDropdown value={sort} label={t("home.sortAria")} align="end" ghost
      options={(["activity", "name", "kind"] as const).map(value => ({ value, label: t(`home.sort.${value}`) }))}
      onChange={value => { usage.used(`home_sort_${value as LibrarySort}`); onSortChange(value as LibrarySort); }}
      triggerProps={{ "aria-label": t("home.sortByAria", { sort: t(`home.sort.${sort}`) }) }} /></span> : null;
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
  // The way back to the document just left: the scale's outline button, its name the first to give way, and the key
  // that does the same after it (left out where nothing hovers: a finger has no Escape).
  const backControl = back && from ? <Button variant="outline" size="control" className="min-w-0 shrink" aria-keyshortcuts="Escape" onClick={back} data-library-back="">
    <span className="truncate">{t("home.backTo", { name: from.name })}</span><Kbd className="[@media(hover:none)]:hidden" aria-hidden="true">{ESCAPE_KEY}</Kbd></Button> : null;
  // The place's name, the page's one heading; on a project's page, the folder's path: each part but the last a way back
  // up to its folder, muted and the first to give way (down to its first letters), the last the folder on screen.
  const TITLE_CLASS = "m-0 min-w-0 truncate text-heading text-foreground";
  const title = crumbs.length > 1 ? <div className="flex min-w-0 flex-initial items-baseline justify-end gap-1 overflow-hidden" data-library-crumbs="">
    {crumbs.slice(0, -1).map(crumb => <Fragment key={crumb.path}>
      <PressTarget className="max-w-[16em] min-w-[2ch] flex-[0_1000_auto] truncate rounded-control text-heading text-muted-foreground no-underline outline-none hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/45 focus-visible:ring-inset"
        href={hrefOf?.({ home: projectFolder(shownProject?.id ?? "", crumb.path) }) ?? null} data-library-crumb=""
        onPress={() => visit(place.view === "project" ? projectFolder(place.project, crumb.path) : place)}>{crumb.name}</PressTarget>
      <span className="flex-none text-heading font-normal text-muted-foreground" aria-hidden="true">/</span>
    </Fragment>)}
    <h2 className={cn(TITLE_CLASS, "flex-initial")} data-library-title="">{shownAs}</h2>
  </div> : <h2 className={TITLE_CLASS} data-library-title="">{placeName}</h2>;
  // Nothing at all yet: no project, no document.
  const empty = !all.length && !(projects ?? []).length;
  // The place with nothing to list says why, in a line.
  const nothing = place.view === "project" ? t("home.projectEmpty") : place.view === "pinned" ? t("home.pinnedEmpty")
    : place.view === "standalone" ? t("home.standaloneEmpty") : t("home.recentsEmpty");
  // Nothing at all yet: the C mark, two controls tall, the welcome's title in the heading step, one muted line 4px
  // under it, then 16px apart the two ways in and the formats the viewer opens; a column centred in the place.
  const welcome = <div className="flex flex-col items-center gap-4 p-4 text-center" data-library-empty="">
    <img src={logo} alt="" draggable={false} className="block size-[calc(var(--cad-control)*2)] select-none" />
    <div className="flex flex-col gap-1">
      <h2 className="m-0 text-heading text-foreground">{t("home.emptyTitle")}</h2>
      <p className="m-0 text-muted-foreground">{t("home.emptyBody")}</p>
    </div>
    {importFile || importFolder ? <div className="flex flex-wrap justify-center gap-2">
      {importFile ? <Button variant="outline" size="control" onClick={importFile}><FolderOpen aria-hidden="true" />{t("home.importFileButton")}</Button> : null}
      {importFolder ? <Button variant="outline" size="control" onClick={importFolder}><Folder aria-hidden="true" />{t("home.importFolderButton")}</Button> : null}
    </div> : null}
    <p className="m-0 text-tiny text-muted-foreground" aria-hidden="true">{WELCOME_FORMATS}</p>
  </div>;
  // A place with nothing to list, or nothing that matches, says so in one muted line, where its first row would stand.
  const line = (state: string, text: string, status = false) => <p className="m-0 text-muted-foreground" role={status ? "status" : undefined} data-library-state={state}>{text}</p>;
  const reading = place.view === "project" ? !listing && !folderRead?.failed && Boolean(library.folder) : items === null;
  const body = items === null || awaited ? <Placeholders layout={layout} />
    : place.view === "project" && !shownProject ? line("gone", projectsFailed ? t("home.projectsFailed") : t("home.projectGone"))
      : shownProject?.missing ? line("missing", t("home.projectMissing"))
        : reading ? <Placeholders layout={layout} />
          : place.view === "project" && !listing && folderRead?.failed ? line("failed", t("home.folderFailed"))
            : empty && place.view === "recents" ? welcome
              : !inPlace.length && !folders.length ? line("empty", searching ? t("home.noMatchingModels") : nothing)
                : !matching.length && !folders.length ? line("unmatched", t("home.noMatchingModels"), true)
                  : <>
                    {documents(matching)}
                    {listing?.truncated ? <p className="m-0 text-muted-foreground" data-library-truncated="">{t("home.projectTruncated")}</p> : null}
                  </>;
  return <div className="cad-library flex size-full flex-col bg-background text-ui" data-library-layout={layout} data-library-place={here}>
    {/* Home's own controls: in the navbar where there is one (`slots`), else in a bar of the page's own, the navbar's row
        on the panel's inset. */}
    {slots ? <>
      {slots.left ? createPortal(heading, slots.left) : null}
      {slots.right ? createPortal(<>{search}{importMenu}</>, slots.right) : null}
    </> : <div className={cn(NAVBAR_ROW_CLASS, "justify-between border-border bg-sidebar px-(--panel-inset)")} data-library-bar="">{heading}<div className="flex items-center gap-2">{search}{importMenu}</div></div>}
    <LibraryFrame places={places} panel={panel} onPanelChange={onPanelChange}>
      {/* A page: it scrolls, with the platform's own scrollbar, only when there is more of it than fits. Padded by the
          panel's inset on every side (more below, clear of a host's composer floating over the bottom), its blocks 16px
          apart; its rows hang past that line as the panel's do (`PANEL_ROW_VARIABLES`). */}
      <main className="@container grid min-w-0 flex-1 auto-rows-max grid-cols-1 content-start gap-4 overflow-y-auto p-(--panel-inset) pb-[calc(var(--cad-host-bottom-inset,0px)+var(--panel-inset))]"
        aria-label={t("home.modelsAria")} style={PANEL_ROW_VARIABLES as React.CSSProperties} data-library-content="">
        {/* The place's heading row, every control the scale's: its name (a project's folder's path, with its glyph, its
            folder from `~` at the project's top and its ⋯) and the way back at the left; Sort and the layout at the right.
            It keeps its shape from place to place. 8px under it, the kinds' chips, where the place holds more than one kind. */}
        <div className="grid grid-cols-1 gap-2">
          <div className="flex min-h-control flex-wrap items-center justify-between gap-x-4 gap-y-2" data-library-toolbar="filters">
            <div className="flex min-w-0 flex-auto items-center gap-2">
              {shownProject ? <Folder className="size-glyph flex-none text-muted-foreground" aria-hidden="true" /> : null}
              {title}
              {shownProject && !folderPath ? <TooltipHint content={folderOnScreen} overflowOnly>
                <span className="min-w-0 flex-[0_100000_auto] truncate text-muted-foreground" data-library-path="">{tildePath(folderOnScreen, home)}</span></TooltipHint> : null}
              {shownProject ? projectMenu(shownProject) : null}
              {backControl}
            </div>
            <div className="flex flex-wrap items-center gap-2">{sortMenu}{layoutSwitch}</div>
          </div>
          {kindRow}
        </div>
        {error ? <p className="m-0 text-destructive" role="alert" data-library-error="">{error}</p> : null}
        {note && note.at === here ? <p className="m-0 text-foreground" role="status" data-library-note="">{note.text}</p> : null}
        {body}
      </main>
    </LibraryFrame>
  </div>;
}
