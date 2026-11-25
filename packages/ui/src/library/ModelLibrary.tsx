import { Fragment, useCallback, useEffect, useLayoutEffect, useRef, useState, type ChangeEvent, type ComponentType, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Box, ChevronDown, Clock, Ellipsis, Files, Folder, FolderOpen, LayoutGrid, List, Pin, Search } from "lucide-react";
import { Button } from "../primitives/button.jsx";
import { ValueDropdown } from "../primitives/value-dropdown.jsx";
import { Pill } from "../primitives/pill.jsx";
import { SegmentedControl } from "../primitives/segmented-control.jsx";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuSeparator, DropdownMenuTrigger } from "../primitives/dropdown-menu.jsx";
import { FieldLabel } from "../primitives/field-label.jsx";
import { Input } from "../primitives/input.jsx";
import { Spinner } from "../primitives/spinner.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { useI18n } from "../i18n/index.js";
import type { LibraryLayout, LibrarySort } from "../tab-store/tabRecord.js";
import { entryMenu } from "../file-viewer/navigation/entry-menu.js";
import type { EntryAction } from "../file-viewer/navigation/index.js";
import type { FileActions } from "../file-viewer/types.js";
import { useViewerMobile } from "../file-viewer/responsive.js";
import type { HomeLocation, NavigationTarget, ViewerHost } from "../host/types.js";
import { documentTarget, folderPlace as projectFolder } from "../host/addresses.js";
import { useControlUsage } from "../usage/controls.js";
import { useNavbarSlots } from "../file-viewer/navbarSlots.js";
import { activityLabel, ageLabel, lastActivity } from "../lib/age.js";
import { hasOpenPopup, ownsEscape } from "../lib/popups.js";
import { plainClick } from "./LibraryPlaces.jsx";
import { LibraryFrame } from "./LibrarySidebar.jsx";
import logo from "../assets/logo-c.svg";

/** A document: a CAD file the host lists, in its library or in a project's folder. */
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
   * The home's kinds read it (`documentKind`); a row without it is known by its file's extension.
   */
  documentKind?: string;
}

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
 * One folder of a project as the host reads it (a CAD host's `CadProjectFolder`): its subfolders that hold a CAD file
 * somewhere below, in the folder's order, then its CAD files; or, asked with words, every CAD file below it that holds
 * them, and no folders. `truncated`: not all of it is listed.
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
/** What a card's badge and a row's Kind say: a model's `labels` (`ModelLabels`), else a file's format ("STEP", "KiCad PCB"). */
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
   * One folder of a project (`path`, below its root; the root with none), or with words (`q`) every CAD file anywhere
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

// A card's or a row's picture, read once it is on screen: the one its row names, else its format's tile. Every picture
// is the light viewport's, on the model area's light gradient in both themes. A card's carries its format's badge
// (`badge`).
function Thumbnail<Model extends LibraryModel>({ item, load, opening = false, badge = null }: { item: Model; load(item: Model): Promise<string | null>; opening?: boolean; badge?: string | null }) {
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
  return <span className="cad-library-thumbnail" ref={element}>
    {image ? <img src={image} alt="" /> : <Box strokeWidth={1} aria-hidden="true" />}
    {badge ? <span className="cad-library-format" aria-hidden="true">{badge}</span> : null}
    {opening ? <span className="cad-library-opening"><Spinner aria-label={t("home.openingAria", { name: item.name })} /></span> : null}
  </span>;
}

/**
 * The list's header row: Name, then where each is (a search on a project's page: Where; Recents and Pinned: Project;
 * `where`), Kind, Size, Updated, Created, over the columns its rows draw (a label each, for the eye: a row names itself).
 */
function Columns({ where = null }: { where?: string | null }) {
  const { t } = useI18n();
  return <div className="cad-library-columns" aria-hidden="true">
    <span>{t("home.columnName")}</span>{where ? <span data-column="where">{where}</span> : null}
    <span data-column="kind">{t("home.columnKind")}</span><span data-column="size">{t("home.columnSize")}</span>
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
 * A card's, a row's or a place's press target: a real link where it has an address (`href`), so the browser's own ways
 * of opening one in a new tab work on it (⌘ or Ctrl and a click, a middle click, the link's menu) and a plain click is
 * `onPress`, in this view; a button where it has none, or cannot be opened (`disabled`).
 */
function PressTarget({ href = null, disabled = false, onPress, children, ...props }: {
  href?: string | null; disabled?: boolean; onPress(): void; children: ReactNode; className?: string;
  "aria-label"?: string; "aria-busy"?: boolean;
}) {
  if (href && !disabled) return <a href={href} onClick={event => { if (!plainClick(event)) return; event.preventDefault(); onPress(); }} {...props}>{children}</a>;
  return <button type="button" disabled={disabled} onClick={onPress} {...props}>{children}</button>;
}

/** Escape's key, as a keyboard prints it: a key's name, the same in every language. */
const ESCAPE_KEY = "Esc";
/** The home narrower than this is on the narrow page's gutters (16px), as a phone's is. */
const NARROW_PX = 720;
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
 * the heading), that folder from `~` and its ⋯ (Open in new tab, Copy path, Reveal, then Remove from CAD, which forgets
 * the project and nothing on disk); then Sort (Last activity, Name, Kind) and grid or list, one segmented control.
 * Under it the kinds' chips (`kindChips`: All, 3D models, Drawings, Boards, Schematics, Robots, each the place holds,
 * with its count under the search), where it holds more than one.
 *
 * A project's page is one folder of it (`library.folder`, read again every `LIST_MS`): its subfolders first, each its
 * glyph and its name and a way into it, then the CAD files directly in it. Recents, Pinned and Standalone are the
 * library's rows. Each document is a card (a picture badged with its format -- for an `.xbf` file "Part" or
 * "Assembly", by its `parts`, "XBF" (its format) where that is not known -- over the name and a line: its project's
 * name in Recents and Pinned, then its last activity with its verb; no glyph or size, which the list has) or a row
 * (Name, Where or Project, Kind: its format, Size, Updated, Created). A card's picture is the one its row names, else its
 * format's tile: the home draws none. A card's or a row's main press is a link where the host gives the document an
 * address (it is named by its `id`; a row with none by its `path`), a button otherwise. Each has a pin and one ⋯ menu:
 * Open, Open in new tab (or Open in browser: `navigation.openBeside`), Copy path, Copy link and Reveal where the host
 * can, Pin or Unpin, then, but on a project's page (where a file is listed for being in the folder), Remove from Recents,
 * which forgets the library's entry of it (no question: its file is untouched, and opening it again brings it back) and
 * takes the card off the list at once. Nothing on the home deletes a file.
 *
 * The search narrows the place on screen: Recents, Pinned and Standalone by the rows in hand; a project's page asks the
 * host for every CAD file below the folder on screen (`library.folder` with `q`), the one place its levels are
 * flattened, each row saying where it is below that folder.
 *
 * Narrower than `NARROW_PX`, and at the phone's scale, the place is on 16px gutters, 12px under the navbar.
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
  // is shown; with words typed, every CAD file below it that holds them, asked once typing rests (the last answer
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
  // The narrow page's gutters at the phone's scale, and in a home narrower than `NARROW_PX` (measured on the home,
  // never the window).
  const mobile = useViewerMobile();
  const [element, setElement] = useState<HTMLDivElement | null>(null);
  const [tight, setTight] = useState(false);
  useLayoutEffect(() => {
    if (!element) return undefined;
    const measure = () => { const width = element.getBoundingClientRect().width; setTight(width > 0 && width < NARROW_PX); };
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  const narrow = mobile || tight;
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
  // A card's pin and its one menu (Open, Open in new tab, what the host can do with a file on disk, Pin or Unpin, then
  // Remove from Recents), there while the pointer is on the card (Figma's star): the pin toggles, and a pinned card
  // shows it, filled, whatever the pointer does. On a project's page there is no Remove from Recents: a file is there
  // because it is in the folder. Nothing here deletes a file: that is the person's own act, in their file manager.
  // Pin or Unpin, from the card's pin or its menu: counted alike.
  const pin = (item: Model) => { usage.used(item.pinned ? "home_unpin" : "home_pin"); void change(item.pinned ? "unpin" : "pin", item); };
  const removable = place.view !== "project";
  const actions = (item: Model) => <div className="cad-library-actions" data-pinned={item.pinned || undefined}>
    <Button variant="ghost" size="icon-xs" className="cad-library-pin" aria-label={t(item.pinned ? "home.unpin" : "home.pin")} aria-pressed={item.pinned}
      onClick={() => pin(item)}><Pin aria-hidden="true" fill={item.pinned ? "currentColor" : "none"} /></Button>
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-xs" aria-label={t("home.actionsAria", { name: item.name })}><Ellipsis aria-hidden="true" /></Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-40">
        <DropdownMenuItem disabled={item.missing} onSelect={() => open(item)}>{t("home.menuOpen")}</DropdownMenuItem>
        {beside ? <DropdownMenuItem disabled={item.missing} onSelect={() => openBeside(targetOf(item), "home_open_new_tab")}>{besideLabel}</DropdownMenuItem> : null}
        {fileItems.map(entry => <DropdownMenuItem key={entry.action} onSelect={() => perform(entry.action, item)}>{entry.label}</DropdownMenuItem>)}
        <DropdownMenuItem onSelect={() => pin(item)}>{t(item.pinned ? "home.unpin" : "home.pin")}</DropdownMenuItem>
        {removable ? <>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={() => remove(item)}>{t("home.removeFromRecents")}</DropdownMenuItem>
        </> : null}
      </DropdownMenuContent>
    </DropdownMenu>
  </div>;
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
  const projectMenu = (project: LibraryProject) => besidePlaces || folderItems.length || removeProject ? <div className="cad-library-place-actions">
    <DropdownMenu modal={false}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon-xs" aria-label={t("home.projectActionsAria", { name: project.name })}><Ellipsis aria-hidden="true" /></Button>
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
    </DropdownMenu>
  </div> : null;
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
  // A row's picture is small, 40 by 28, its spinner over it while it is being opened.
  const name = (item: Model) => <span className="cad-library-name">
    <Thumbnail item={item} load={load} opening={opening === item.path} />
    <span className="cad-library-label">{item.name}</span>
  </span>;
  // A row's columns: where it is, its kind and size, then its two times with no verb: when it last changed, and when the library first knew it.
  const columns = (item: Model) => <>
    {whereColumn ? <span className="cad-library-status" data-column="where">{where(item)}</span> : null}
    <span className="cad-library-status" data-column="kind">{format(item)}</span>
    <span className="cad-library-status" data-column="size">{sizeLabel(item.size, locale) || "—"}</span>
    <span className="cad-library-status" data-column="updated">{item.missing ? t("home.fileUnavailable") : age(item.updated)}</span>
    <span className="cad-library-status" data-column="created">{age(item.created)}</span>
  </>;
  // A document's entry: its main press, a link where the host gives it an address, then its pin and ⋯.
  const entry = (item: Model, className: string, body: ReactNode) => <li key={item.path} className={className} data-missing={item.missing || undefined}
    data-opening={opening === item.path || undefined} data-from={left(item) || undefined} ref={left(item) ? ringed : undefined}>
    <div className="cad-library-main">
      <PressTarget className="cad-library-open" href={item.missing ? null : hrefOf?.(targetOf(item)) ?? null} disabled={item.missing}
        aria-label={t("home.openAria", { name: item.name })} aria-busy={opening === item.path || undefined} onPress={() => open(item)}>{body}</PressTarget>
      {actions(item)}
    </div>
  </li>;
  // A subfolder of the folder on screen: its glyph and its name, a way into it (a real link where the host gives places
  // an address), and nothing else.
  const folderPlace = (folder: LibraryFolderRef): HomeLocation => projectFolder(place.view === "project" ? place.project : "", folder.path);
  const folderEntry = (folder: LibraryFolderRef, className: string, body: ReactNode) => <li key={folder.path} className={className} data-folder="">
    <div className="cad-library-main">
      <PressTarget className="cad-library-open" href={hrefOf?.({ home: folderPlace(folder) }) ?? null} aria-label={t("home.openAria", { name: folder.name })}
        onPress={() => visit(folderPlace(folder))}>{body}</PressTarget>
    </div>
  </li>;
  const folderName = (folder: LibraryFolderRef) => <span className="cad-library-name">
    <span className="cad-library-folder-glyph"><Folder aria-hidden="true" /></span>
    <span className="cad-library-label">{folder.name}</span>
  </span>;
  // The place's folders and documents, as cards or as rows under their header: the folders first, then the documents.
  const documents = (list: readonly Model[]) => layout === "list"
    ? <div className="cad-library-table" data-where={whereColumn ? "" : undefined}><Columns where={whereColumn} /><ul className="cad-library-list" aria-label={t("home.filesAria")}>
      {folders.map(folder => folderEntry(folder, "cad-library-row", <>{folderName(folder)}
        {whereColumn ? <span className="cad-library-status" data-column="where" /> : null}
        {["kind", "size", "updated", "created"].map(column => <span key={column} className="cad-library-status" data-column={column}>—</span>)}</>))}
      {list.map(item => entry(item, "cad-library-row", <>{name(item)}{columns(item)}</>))}</ul></div>
    : <>
      {folders.length ? <ul className="cad-library-folders" aria-label={t("home.foldersAria")}>
        {folders.map(folder => folderEntry(folder, "cad-library-folder", folderName(folder)))}</ul> : null}
      {list.length ? <ul className="cad-library-grid" aria-label={t("home.filesAria")}>{list.map(item => entry(item, "cad-library-card", <>
        <Thumbnail item={item} load={load} opening={opening === item.path} badge={format(item)} />
        {/* The caption: the name over its one line. No glyph: the picture and its badge say what it is. */}
        <span className="cad-library-body">
          <span className="cad-library-text">
            <span className="cad-library-label">{item.name}</span>
            <span className="cad-library-status">{status(item)}</span>
          </span>
        </span>
      </>))}</ul> : null}
    </>;
  // Import, the host's chooser of a file or a folder: neutral, as every control of the row is (never a filled primary).
  const importMenu = importFile || importFolder ? <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild>
      <Button variant="outline" size="xs" className="cad-library-pick h-control gap-1.5 px-2.5 text-ui" aria-label={t("home.import")}>
        <FolderOpen className="size-4" aria-hidden="true" /><span className="cad-library-pick-label">{t("home.import")}</span><ChevronDown className="size-3.5 text-muted-foreground" aria-hidden="true" /></Button>
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
  // The page's heading: "Home", in the navbar where there is one.
  const heading = <h1 className="cad-library-heading" data-library-heading={slots ? "navbar" : "page"}>{t("home.title")}</h1>;
  // Sort: a muted label and the one value dropdown (`primitives/value-dropdown.jsx`), drawn as the row's ghost control.
  const CHOICE_CLASS = "cad-library-choice min-w-0 w-auto gap-1 border-0 bg-transparent px-2 shadow-none hover:bg-accent dark:bg-transparent";
  // The kinds: a row of pills (`primitives/pill.jsx`) under the heading row, All then each kind the place holds, with its
  // count; one on at a time.
  const kindRow: ReactNode = chips.length ? <div className="cad-library-kinds" role="group" aria-label={t("home.kindsAria")} data-library-kinds="">
    {chips.map(chip => <Pill key={chip.kind} pressed={chip.kind === shownKind} count={chip.count} data-kind={chip.kind}
      aria-label={t("home.kindCount", { kind: t(`home.kind.${chip.kind}`), count: chip.count })}
      onClick={() => { if (chip.kind !== shownKind) usage.used(`home_kind_${chip.kind}`); setKind(chip.kind); }}>{t(`home.kind.${chip.kind}`)}</Pill>)}
  </div> : null;
  const sortMenu: ReactNode = onSortChange ? <span className="cad-library-field"><FieldLabel className="cad-library-field-label">{t("home.sortAria")}</FieldLabel>
    <ValueDropdown value={sort} label={t("home.sortAria")} align="end"
      options={(["activity", "name", "kind"] as const).map(value => ({ value, label: t(`home.sort.${value}`) }))}
      onChange={value => { usage.used(`home_sort_${value as LibrarySort}`); onSortChange(value as LibrarySort); }}
      className={`cad-library-sort ${CHOICE_CLASS}`}
      triggerProps={{ "aria-label": t("home.sortByAria", { sort: t(`home.sort.${sort}`) }) }} /></span> : null;
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
  // Grid or list: one segmented control (`primitives/segmented-control.jsx`).
  const layoutSwitch = onLayoutChange ? <SegmentedControl className="cad-library-layout" label={t("home.layout")} value={layout}
    options={[{ value: "grid", label: t("home.grid"), Icon: LayoutGrid }, { value: "list", label: t("home.list"), Icon: List }]}
    onChange={value => { usage.used(`home_layout_${value as LibraryLayout}`); onLayoutChange(value as LibraryLayout); }} /> : null;
  // The way back to the document just left: its name, and the key that does the same (left out where nothing hovers).
  const backControl = back && from ? <Button variant="outline" size="xs" className="cad-library-back" aria-keyshortcuts="Escape" onClick={back}>
    <span className="cad-library-label">{t("home.backTo", { name: from.name })}</span><kbd className="cad-library-key" aria-hidden="true">{ESCAPE_KEY}</kbd></Button> : null;
  // The place's name; on a project's page, the folder's path: each part but the last a way back up to its folder.
  const title = crumbs.length > 1 ? <div className="cad-library-crumbs">
    {crumbs.slice(0, -1).map(crumb => <Fragment key={crumb.path}>
      <PressTarget className="cad-library-crumb" href={hrefOf?.({ home: projectFolder(shownProject?.id ?? "", crumb.path) }) ?? null}
        onPress={() => visit(place.view === "project" ? projectFolder(place.project, crumb.path) : place)}>{crumb.name}</PressTarget>
      <span className="cad-library-crumb-slash" aria-hidden="true">/</span>
    </Fragment>)}
    <h2 className="cad-library-title">{shownAs}</h2>
  </div> : <h2 className="cad-library-title">{placeName}</h2>;
  // Nothing at all yet: no project, no document.
  const empty = !all.length && !(projects ?? []).length;
  // The place with nothing to list says why, in a line.
  const nothing = place.view === "project" ? t("home.projectEmpty") : place.view === "pinned" ? t("home.pinnedEmpty")
    : place.view === "standalone" ? t("home.standaloneEmpty") : t("home.recentsEmpty");
  const welcome = <div className="cad-library-welcome" data-library-empty="">
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
  </div>;
  const reading = place.view === "project" ? !listing && !folderRead?.failed && Boolean(library.folder) : items === null;
  const body = items === null || awaited ? <Placeholders layout={layout} />
    : place.view === "project" && !shownProject ? <p className="cad-library-empty" data-library-state="gone">{projectsFailed ? t("home.projectsFailed") : t("home.projectGone")}</p>
      : shownProject?.missing ? <p className="cad-library-empty" data-library-state="missing">{t("home.projectMissing")}</p>
        : reading ? <Placeholders layout={layout} />
          : place.view === "project" && !listing && folderRead?.failed ? <p className="cad-library-empty" data-library-state="failed">{t("home.folderFailed")}</p>
            : empty && place.view === "recents" ? welcome
              : !inPlace.length && !folders.length ? <p className="cad-library-empty" data-library-state="empty">{searching ? t("home.noMatchingModels") : nothing}</p>
                : !matching.length && !folders.length ? <p className="cad-library-empty" role="status">{t("home.noMatchingModels")}</p>
                  : <>
                    {documents(matching)}
                    {listing?.truncated ? <p className="cad-library-truncated">{t("home.projectTruncated")}</p> : null}
                  </>;
  return <div className="cad-library h-full text-ui" data-library-layout={layout} data-library-narrow={narrow ? "" : undefined} data-library-place={here} ref={setElement}>
    {/* Home's own controls: in the navbar where there is one (`slots`), else in a bar of the page's own. */}
    {slots ? <>
      {slots.left ? createPortal(heading, slots.left) : null}
      {slots.right ? createPortal(<>{search}{importMenu}</>, slots.right) : null}
    </> : <div className="cad-library-bar">{heading}<div className="cad-library-controls">{search}{importMenu}</div></div>}
    <LibraryFrame places={places} panel={panel} onPanelChange={onPanelChange}>
      {/* A page: it scrolls, with the platform's own scrollbar, only when there is more of it than fits. */}
      <main className="cad-library-content overflow-y-auto" aria-label={t("home.modelsAria")}>
        {/* The place's heading row, every control the scale's: its name (a project's folder's path, with its glyph, its
            folder and its ⋯) and the way back at the left; Sort and the layout at the right. It keeps its shape from
            place to place. Under it, the kinds' chips, where the place holds more than one kind. */}
        <div className="cad-library-toolbar" data-library-toolbar="filters">
          <div className="cad-library-place">
            {shownProject ? <Folder className="cad-library-glyph" aria-hidden="true" /> : null}
            {title}
            {shownProject ? <TooltipHint content={folderOnScreen} overflowOnly><span className="cad-library-path truncate">{tildePath(folderOnScreen, home)}</span></TooltipHint> : null}
            {shownProject ? projectMenu(shownProject) : null}
            {backControl}
          </div>
          <div className="cad-library-controls">{sortMenu}{layoutSwitch}</div>
        </div>
        {kindRow}
        {error ? <div className="cad-library-error" role="alert"><p>{error}</p></div> : null}
        {note && note.at === here ? <p className="cad-library-note" role="status">{note.text}</p> : null}
        {body}
      </main>
    </LibraryFrame>
  </div>;
}
