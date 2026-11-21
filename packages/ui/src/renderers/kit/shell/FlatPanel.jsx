import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Boxes, Clapperboard, Cpu, Layers, ListTree, Move3d, MoreHorizontal, Search, SlidersHorizontal, Waypoints } from "lucide-react";
import { useI18n } from "@cad/ui/i18n";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from "@cad/ui/primitives/dropdown-menu";
import { TreeFilterInput } from "@cad/ui/primitives/tree-filter";
import { cn } from "@cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { ChangedDot } from "../tools/ChangedDot.jsx";
import { ToolStackContext } from "../tools/ToolStack.jsx";
import { FilePanelContext, hasLegacyFilePanel, legacyFilePanel, legacyFilePanelTab, readFilePanel, withoutLegacyFilePanel } from "../../../file-viewer/filePanel.js";
import { PanelSurface, usePanelWidth } from "./PanelSurface.jsx";
import { DEFAULT_PANEL_WIDTH, MIN_MODEL_WIDTH } from "./sidebars.js";

/**
 * The view's one panel, the sidebar (`ViewFrame.jsx`), docked at the view's left edge the way KiCad's Appearance
 * panel is: one head row, as Figma's Layers panel's — the tabs at its left, pills as Figma's (a model's Model, then
 * Parameters, Joints and Animation where the file has them; a board's Parts, Nets and Layers; a schematic's Parts, Nets
 * and Hierarchy), or one tab's plain title — and the open tab's page under it, the panel's full height, scrolling as one. What is picked is read in its Quick Edit chip's list, never here. It is one
 * surface of one text size (12px, `globals.css`'s `--cad-text-panel`) and 28px rows, on its 16px keyline, where every control,
 * every line of text not after an icon, and every row's one glyph starts.
 *
 * - **Collapsed, it goes completely**, nothing of it left over the model: its toggle is the navbar's
 *   (`file-viewer/panelToggles.js`). ⌘\ (Ctrl+\) shows and hides it, and / opens it on its search. A mouse resting
 *   on the toggle shows it over the view (`peek`, `usePanelPeek.js`), the same panel, pushing nothing.
 * - **Search** is the panel's one query over its tree-like tabs (`isStructureTab`: the `tree` section, every tab
 *   handed in but one marked `search: false`), never Parameters, Joints or Animation: an icon at the head row's right
 *   end, there only where some tab is searchable. Pressed (or /), the row is the search box, its X where the icon was,
 *   and the tabs stand in a row under it; Escape or the X closes it. A query filters every searchable tab at once, each
 *   tab's name saying how many it finds (`useFlatPanelMatches`); the open tab shows its own, and opened from a tab it
 *   does not cover the search opens the first that it does, then, as a query finds nothing there, the first with
 *   matches. A tab reads the query from `useFlatPanel()` (a tab it does not cover reads none), and a tab whose results
 *   the arrow keys walk registers its keys there (the Parts' and the Nets'): the open tab's get them.
 * - **The tabs** take the head row's width as they fit it, measured; those that do not fit are a ⋯ menu's items at the
 *   row's end, with their icons (`fitTabs`), and the open tab always shows.
 * - **Two ways to be shown**: `docked` beside the canvas, the canvas always the narrower for it, its
 *   width the person's (a grip on its right edge, kept); `page`, on a phone, the whole of the sidebar sheet it is in,
 *   the same head, tabs, search and rows as docked (no grip, no Back); a pick in it closes it.
 *
 * Every tab stays mounted, shown or not, so a tree keeps its expansion; each keeps its own scroll.
 *
 * Its tabs are handed in (`tabs`, a board's and a schematic's), or are the sections drawn in it
 * (`sections`: a 3D view's `ToolPanel`s — its Model tree or Links, Position and the rest — each a tab by its
 * name, in their order, `ToolPanel.jsx`'s tabbed form). `useFlatPanelState` is what a view keeps of it.
 */

/**
 * The panel's state that is the file's (`filePanel.js`): kept in the file's view as its camera is, so a
 * reload brings it back for that file and another file starts at its own — its width (`FLAT_PANEL_DEFAULT_WIDTH` at first) and
 * its tab (the first at first), and the person's choice (`record`, written by `change`: open or closed), which
 * `ViewFrame.jsx` reads with the view's width (`sidebars.js`). `focusSearch` counts
 * the requests to open it on its search (/).
 *
 * A file with no panel of its own starts from the tab's old shared one, where the tab still carries it
 * (`legacyFilePanel`), which is then dropped from the tab's settings and never written there again; a
 * `compact` view (a picture taken out of sight, a host's inline card) only reads it, as its panel is
 * never shown and its file's view is not the one kept.
 * @param {{ frameRef: { current: HTMLElement | null }, kind: string,
 *   toolStack: object, onToolStackChange(patch: (layout: object) => object): void, compact?: boolean }} options
 */
export function useFlatPanelState({ frameRef, kind, toolStack, onToolStackChange, compact = false }) {
  const [frameWidth, setFrameWidth] = useState(0);
  useLayoutEffect(() => {
    const element = frameRef.current;
    if (!element) return undefined;
    const measure = () => setFrameWidth(Math.round(element.getBoundingClientRect().width));
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [frameRef]);
  // The file's panel as it opened (the file viewer's: `FilePanelContext`), or the tab's old shared one.
  const file = useContext(FilePanelContext);
  const fileRef = useRef(file);
  fileRef.current = file;
  const [initial] = useState(() => {
    const own = readFilePanel(file?.panel);
    return Object.keys(own).length ? { panel: own, tabs: null, adopted: false } : { ...legacyFilePanel(toolStack), adopted: true };
  });
  const [panel, setPanel] = useState(initial.panel);
  const panelRef = useRef(panel);
  const change = useCallback(patch => {
    const next = { ...panelRef.current, ...patch };
    for (const key of Object.keys(next)) if (next[key] === undefined) delete next[key];
    panelRef.current = next;
    setPanel(next);
    fileRef.current?.change(next);
  }, []);
  useEffect(() => {
    // A starting value taken from the old shared form is the file's from now on; the shared form goes.
    if (compact) return;
    if (initial.adopted && Object.keys(initial.panel).length) fileRef.current?.change(initial.panel);
    if (hasLegacyFilePanel(toolStack)) onToolStackChange(withoutLegacyFilePanel);
  }, []);
  // Its tab, once the view names its kind (a view reads its file before it has a panel to name).
  const legacyTab = initial.adopted ? legacyFilePanelTab(initial.tabs, kind) : undefined;
  useEffect(() => { if (legacyTab && panelRef.current.tab === undefined) change({ tab: legacyTab }); }, [legacyTab, change]);
  const tab = panel.tab;
  const changeTab = useCallback(id => change({ tab: id }), [change]);
  // The width is one number: the default, or what the person dragged it to, never the view's or the tabs'. The grip
  // alone is bounded, as it moves: it leaves the model `MIN_MODEL_WIDTH` (`sidebars.js`). A narrow view collapses the
  // panel instead (`sidebarLayout`).
  const maxWidth = frameWidth > 0 ? Math.max(FLAT_PANEL_MIN_WIDTH, Math.floor(frameWidth - MIN_MODEL_WIDTH)) : Infinity;
  const width = panel.width ?? FLAT_PANEL_DEFAULT_WIDTH;
  const changeWidth = useCallback(next => change({ width: next }), [change]);
  const [focusSearch, setFocusSearch] = useState(0);
  const askSearch = useCallback(() => setFocusSearch(count => count + 1), []);
  return { frameWidth, record: panel, change, tab, changeTab, width, maxWidth, changeWidth, focusSearch, askSearch };
}

// The panel's lines, surface, head row, scroller and grip are `PanelSurface.jsx`'s.
/**
 * Which tabs the head's row shows, measured: `ids` in order, `widths` each one's drawn width, `room` the row's width
 * for tabs (and the ⋯ menu's button, `more` wide), `gap` between them. Every tab that fits shows; where they do not
 * all fit, the row ends with ⋯ and the tabs that do not fit beside it are its items, in order. The open tab
 * (`active`) always shows: where it would be in the menu it takes the place of the last tab shown (more of them, as
 * its width needs). `{ visible, hidden }`, each a list of ids in the tabs' order but the swapped-in tab, last.
 * @param {{ ids: string[], widths: Map<string, number>, room: number, more: number, gap?: number, active?: string }} options
 */
export function fitTabs({ ids, widths, room, more, gap = 2, active }) {
  const width = list => list.reduce((sum, id, at) => sum + (widths.get(id) ?? 0) + (at ? gap : 0), 0);
  if (width(ids) <= room + 0.5) return { visible: [...ids], hidden: [] };
  const budget = room - more - gap;
  const visible = [];
  for (const id of ids) {
    if (width([...visible, id]) > budget + 0.5) break;
    visible.push(id);
  }
  if (active && ids.includes(active) && !visible.includes(active)) {
    while (visible.length && width([...visible, active]) > budget + 0.5) visible.pop();
    visible.push(active);
  }
  return { visible, hidden: ids.filter(id => !visible.includes(id)) };
}

/** A tab's icon in the ⋯ menu: its own (`icon`), else its kind's by its id. */
const TAB_ICONS = Object.freeze({ tree: Boxes, parameters: SlidersHorizontal, position: Move3d, animation: Clapperboard, parts: Cpu, nets: Waypoints,
  layers: Layers, hierarchy: ListTree });

// The head's row is 32px (the 28px pills and 4px), so with the 8px round it the head's rule is on the strip's bottom
// line. It holds the tabs, then ⋯ where some do not fit, then the search's icon.
/** The sections (`ToolPanel` ids) that are a file's structure, which the search covers: the Model tree, the Links. */
const STRUCTURE_SECTIONS = new Set(["tree"]);
/** Whether the search covers a tab (a tree-like one): a structure section, or a tab handed in unless it says `search: false`. */
export const isStructureTab = (entry, sections) => Boolean(entry) && (sections ? STRUCTURE_SECTIONS.has(entry.id) : entry.search !== false);
export const FLAT_PANEL_DEFAULT_WIDTH = DEFAULT_PANEL_WIDTH;
export const FLAT_PANEL_MIN_WIDTH = 200;
/** The toggle's key, as its tooltip shows it: ⌘\ on a Mac (the host's `environment.platform`), Ctrl+\ elsewhere. */
export const flatPanelShortcut = platform => (platform === "darwin" ? "⌘\\" : "Ctrl+\\");

const FlatPanelContext = createContext(null);
/**
 * The panel a tab is drawn in: `query` (what is typed, `""` for none), `searching`, `page` (a phone's
 * whole-view page), `shown` (the tab is on screen: the panel open, and the tab the one open or every
 * tab's hits listed), `registerKeys(handler)` (the search box's arrow and Enter keys go to `handler`
 * while its tab is open, or while no open tab has a handler; returns the release) and `picked()` (a
 * row pressed: on a phone, the panel gives the view back). Null outside one.
 */
export const useFlatPanel = () => useContext(FlatPanelContext);

/**
 * Whether the panel section `id` (a `ToolPanel` drawn as one of the panel's tabs) is on screen: the panel
 * open, and its tab the one open or the search listing every tab's hits. A tab's own content reads
 * `useFlatPanel().shown`; a section reads this, as it is drawn above the tab it names. True outside a panel.
 */
export function useFlatPanelSection(id) {
  const panel = useContext(FlatPanelContext), stack = useContext(ToolStackContext);
  if (!panel) return true;
  return panel.shown !== false && (!stack?.tabbed || stack.activeSection === id);
}

/**
 * A searchable tab says how many rows the panel's query finds in it (`count`; `null` while nothing is typed), so its
 * name in the head can say it. Outside a panel, or in a tab the search does not cover, it does nothing.
 * @param {number | null | undefined} count
 */
export function useFlatPanelMatches(count) {
  const report = useContext(FlatPanelContext)?.matches;
  useEffect(() => { if (report && count !== undefined) report(count); }, [report, count]);
  useEffect(() => () => report?.(null), [report]);
}

/**
 * A tab's "changed" mark: drawn where its tab's Reset (or Save) is on, from the same state (`on`) that turns it on, so
 * the dot on the tab's name and the button never disagree. Rendered beside that button, inside the tab; draws nothing.
 * @param {{ on: boolean }} props
 */
export function FlatPanelChanged({ on }) {
  const mark = useContext(FlatPanelContext)?.markChanged;
  useEffect(() => { mark?.(on === true); }, [mark, on]);
  useEffect(() => () => mark?.(false), [mark]);
  return null;
}

// A tab's own view of the panel: its keys registered under its id, whether it is on screen, and the query where the
// search covers it (none where it does not), its matches and its changed state told back under its id.
function FlatPanelTab({ panel, id, shown, children }) {
  const { registerKeys, report, searchable, setChanged } = panel;
  const covered = searchable?.has(id) ?? false;
  const value = useMemo(() => ({ ...panel, shown: panel.shown && shown, query: covered ? panel.query : "", searching: covered && panel.searching,
    registerKeys: handler => registerKeys(handler, id), matches: covered && report ? count => report(id, count) : null,
    markChanged: setChanged ? on => setChanged(id, on) : null }), [panel, id, shown, covered, registerKeys, report, setChanged]);
  return <FlatPanelContext.Provider value={value}>{children}</FlatPanelContext.Provider>;
}

/** A section drawn as one of the panel's tabs (`ToolPanel.jsx`'s tabbed form): its children see the panel as that tab. */
export function FlatPanelSectionScope({ id, children }) {
  const panel = useContext(FlatPanelContext), stack = useContext(ToolStackContext);
  if (!panel || !stack?.tabbed) return children;
  return <FlatPanelTab panel={panel} id={id} shown={stack.activeSection === id}>{children}</FlatPanelTab>;
}

/**
 * @param {{ mode: "docked" | "page", open: boolean, onClose(): void, label: string,
 *   searchLabel: string, tabs: { id: string, label: string, content: import("react").ReactNode, search?: boolean, icon?: import("react").ComponentType }[],
 *   tab: string, onTabChange(id: string): void, width: number, maxWidth: number, onWidthChange(width: number): void,
 *   focusSearch: number, peek?: boolean, surfaceRef?: import("react").Ref<HTMLElement>, surfaceProps?: object | null }} props
 *   `focusSearch`: a count; each new value opens the search with the keyboard in its box (/). `peek`: the collapsed
 *   panel shown over the view on a rest on its toggle (`usePanelPeek.js`), its surface `surfaceRef` and its pointer
 *   handlers `surfaceProps`.
 */
export default function FlatPanel({ mode, open, onClose, label, searchLabel, tabs: given = null, sections = null, tab, onTabChange, width, maxWidth, onWidthChange, focusSearch, hidden = false,
  peek = false, surfaceRef, surfaceProps = null }) {
  const { t } = useI18n();
  const page = mode === "page";
  const [searchOpen, setSearchOpen] = useState(false);
  const [query, setQuery] = useState("");
  const searching = searchOpen && query.trim() !== "";
  // The search box's arrows and Enter go to the open tab's list, else to the first tab that has one.
  const keys = useRef(new Map());
  const registerKeys = useCallback((handler, tabId = "") => {
    keys.current.set(tabId, handler);
    return () => { if (keys.current.get(tabId) === handler) keys.current.delete(tabId); };
  }, []);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const picked = useCallback(() => { if (page) closeRef.current(); }, [page]);
  // On screen: the panel open (a tab narrows it to its own, below).
  const onScreen = open && !hidden;

  // A section drawn in the panel names its tab (`ToolPanel.jsx`); the tabs are in the sections' order.
  const body = useRef(null);
  const [registered, setRegistered] = useState([]);
  const names = useRef(new Map());
  const register = useCallback((id, name) => {
    names.current.set(id, name);
    setRegistered(current => (current.some(entry => entry.id === id && entry.label === name) ? current : [...current.filter(entry => entry.id !== id), { id, label: name }]));
    return () => { names.current.delete(id); setRegistered(current => current.filter(entry => entry.id !== id)); };
  }, []);
  useLayoutEffect(() => {
    if (!sections || !body.current) return;
    const order = [...body.current.querySelectorAll(":scope > [data-flat-panel-section]")].map(element => element.getAttribute("data-flat-panel-section"));
    setRegistered(current => {
      const next = [...current].sort((a, b) => order.indexOf(a.id) - order.indexOf(b.id));
      return next.every((entry, at) => entry === current[at]) ? current : next;
    });
  });
  const tabs = given ?? registered;
  // The tabs the search covers, and how many rows it finds in each (told by the tabs, `useFlatPanelMatches`).
  const searchableKey = tabs.filter(entry => isStructureTab(entry, sections)).map(entry => entry.id).join("\u0000");
  const searchable = useMemo(() => new Set(searchableKey ? searchableKey.split("\u0000") : []), [searchableKey]);
  const [counts, setCounts] = useState({});
  const report = useCallback((id, count) => setCounts(current => (current[id] === count ? current : { ...current, [id]: count })), []);
  // The tabs whose state is off its default (`FlatPanelChanged`): a dot on each one's name.
  const [changed, setChangedState] = useState({});
  const setChanged = useCallback((id, on) => setChangedState(current => (Boolean(current[id]) === on ? current : { ...current, [id]: on })), []);
  // Drawn as sections, a tree reads the panel where it draws its section (`ToolPanel`, `tree`): its matches are that tab's.
  const sectionMatches = useMemo(() => (sections ? count => report("tree", count) : null), [Boolean(sections), report]);
  const panel = useMemo(() => ({ query, searching, page, shown: onScreen, registerKeys, picked, searchable, report, matches: sectionMatches, setChanged }),
    [query, searching, page, onScreen, registerKeys, picked, searchable, report, sectionMatches, setChanged]);

  // Each tab keeps its own scroll.
  const scroller = useRef(null), scrolls = useRef(new Map());
  const lastKey = useRef(tab);
  useLayoutEffect(() => {
    const element = scroller.current;
    if (!element || lastKey.current === tab) return;
    scrolls.current.set(lastKey.current, element.scrollTop);
    lastKey.current = tab;
    element.scrollTop = scrolls.current.get(tab) ?? 0;
  }, [tab]);

  const input = useRef(null), head = useRef(null);
  const closeSearch = useCallback(() => { setQuery(""); setSearchOpen(false); }, []);
  const onSearchKeyDown = event => {
    if (event.key === "Escape") {
      event.preventDefault();
      event.stopPropagation();
      closeSearch();
      return;
    }
    const handler = keys.current.get(activeRef.current) ?? keys.current.values().next().value;
    handler?.(event);
  };
  // A phone's page goes with Escape, wherever its focus is.
  const onPanelKeyDown = event => {
    if (!page || event.key !== "Escape" || event.defaultPrevented) return;
    event.preventDefault();
    event.stopPropagation();
    onClose();
  };
  // The width: the person's, from the grip on the right edge, one write when it lets go (`PanelSurface.jsx`).
  const { drawnWidth, grip } = usePanelWidth({ width, minWidth: FLAT_PANEL_MIN_WIDTH, maxWidth, onWidthChange });

  const active = tabs.some(entry => entry.id === tab) ? tab : tabs[0]?.id;
  const activeRef = useRef(active);
  activeRef.current = active;
  const firstSearchable = tabs.find(entry => searchable.has(entry.id))?.id;
  // A tab chosen by hand while a query is on stays chosen: the search moves to the tab with matches only until then.
  const chosen = useRef(false);
  const chooseTab = useCallback(id => { chosen.current = true; onTabChange(id); }, [onTabChange]);
  const openSearch = useCallback(() => {
    if (firstSearchable === undefined) return;
    chosen.current = false;
    // Opened from a tab it does not cover, the search opens the first it does.
    if (!searchable.has(activeRef.current)) onTabChange(firstSearchable);
    setSearchOpen(true);
    setFocusAsked(count => count + 1);
  }, [firstSearchable, searchable, onTabChange]);
  useEffect(() => { chosen.current = false; }, [query]);
  // A query that finds nothing in the open tab, and something in another: that tab, the first, unless one was chosen.
  useEffect(() => {
    if (!searching || chosen.current) return;
    const here = counts[activeRef.current];
    if (searchable.has(activeRef.current) && here !== 0 && here != null) return;
    const next = tabs.find(entry => searchable.has(entry.id) && counts[entry.id] > 0)?.id;
    if (next && next !== activeRef.current) onTabChange(next);
  }, [searching, counts, searchable, tabs, onTabChange]);
  // / (each new count once, when the panel is open: a reopened or remounted panel takes no focus) opens the search.
  const searched = useRef(focusSearch);
  const [focusAsked, setFocusAsked] = useState(0);
  useEffect(() => {
    if (!open || focusSearch === searched.current) return;
    searched.current = focusSearch;
    openSearch();
  }, [focusSearch, open, openSearch]);
  useLayoutEffect(() => {
    if (!focusAsked) return;
    input.current?.focus();
    input.current?.select?.();
  }, [focusAsked, searchOpen]);
  // The search goes with the last tab it covers.
  useEffect(() => { if (searchOpen && firstSearchable === undefined) closeSearch(); }, [searchOpen, firstSearchable, closeSearch]);

  // One tab is a plain title, the open tab's name in its place (no pill, no fill), and the head's rule goes, so the
  // title flows straight into its list: the head a list row's height (28px), the title on the rows' icons' line (the
  // inset, `--panel-inset`, as a tab's name is), the list 4px under it. Several are pills over the rule.
  const single = tabs.length === 1 ? tabs[0] : null;
  const compactHead = Boolean(single) && !searchOpen;
  const countOf = id => (searching && searchable.has(id) ? counts[id] ?? null : null);

  // The row's tabs as they fit it, measured (`fitTabs`): a hidden ruler draws every tab as the row would, and the row
  // says how wide it is; both are watched, so a resize, a translation or a count measures again.
  const row = useRef(null), ruler = useRef(null);
  const ids = tabs.map(entry => entry.id);
  const [fitted, setFitted] = useState(null);
  const measure = useCallback(() => {
    // Layout widths (`offsetWidth`, untouched by a transform); a row or a tab not laid out (0) is not measured: every tab shows.
    const room = row.current?.offsetWidth ?? 0, rulers = ruler.current;
    const widths = new Map([...(rulers?.querySelectorAll("[data-tab-ruler]") ?? [])].map(node => [node.getAttribute("data-tab-ruler"), node.offsetWidth]));
    if (!room || !widths.size || [...widths.values()].some(value => !value)) { setFitted(null); return; }
    // ⋯ and the 4px before it, less the tabs' own gap `fitTabs` counts.
    const more = (rulers.querySelector("[data-more-ruler]")?.offsetWidth || 28) + ICON_GAP_PX - TAB_GAP_PX;
    const next = fitTabs({ ids: [...widths.keys()], widths, room, more, gap: TAB_GAP_PX, active: activeRef.current });
    setFitted(current => (current && current.visible.join() === next.visible.join() && current.hidden.join() === next.hidden.join() ? current : next));
  }, []);
  const countKey = ids.map(id => countOf(id) ?? "").join();
  useLayoutEffect(() => { measure(); }, [measure, ids.join(), tabs.map(entry => entry.label).join(), countKey, active, single, open, hidden, searchOpen]);
  useLayoutEffect(() => {
    if (typeof ResizeObserver === "undefined" || !row.current) return undefined;
    const observer = new ResizeObserver(() => measure());
    observer.observe(row.current);
    if (ruler.current) observer.observe(ruler.current);
    return () => observer.disconnect();
  }, [measure, single, open, hidden, searchOpen]);
  const visible = fitted ? fitted.visible.filter(id => ids.includes(id)) : ids;
  const hiddenTabs = fitted ? tabs.filter(entry => fitted.hidden.includes(entry.id)) : [];

  const tabbed = useMemo(() => ({ tabbed: true, activeSection: active, searching, register }), [active, searching, register]);
  const ids_ = id => ({ tab: `flat-panel-tab-${id}`, panel: `flat-panel-body-${id}` });
  const tabName = (entry, on, ruled = false) => {
    const count = countOf(entry.id);
    return <>
      {/* The open tab's name is medium weight; every tab is as wide as its name in that weight (an unseen copy holds
          it), so choosing one moves nothing. */}
      <span className="relative grid justify-items-center">
        <span aria-hidden="true" className="invisible col-start-1 row-start-1 font-medium">{entry.label}</span>
        {/* Against the name's top-right, outside its box: the tab's width and its name's place never move for it. */}
        {changed[entry.id] && !ruled ? <ChangedDot className="-right-[5px] -top-px" /> : null}
        <span className={cn("col-start-1 row-start-1", on && "font-medium")} data-flat-panel-tab-name={ruled ? undefined : ""}>{entry.label}</span>
      </span>
      {count !== null ? <span className="ml-1 tabular-nums text-muted-foreground" data-flat-panel-tab-count={ruled ? undefined : ""}>{count}</span> : null}
    </>;
  };
  const TAB_CLASS = "flex h-7 shrink-0 items-center whitespace-nowrap rounded-md px-2 text-ui transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45";
  const ICON_BUTTON_CLASS = "grid size-7 shrink-0 place-items-center rounded-md text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45 aria-expanded:bg-accent aria-expanded:text-foreground [&_svg]:size-3.5";
  const tabButton = entry => {
    const on = entry.id === active;
    return <button key={entry.id} type="button" role="tab" id={ids_(entry.id).tab} aria-controls={ids_(entry.id).panel} aria-selected={on} tabIndex={on ? 0 : -1}
      aria-label={changed[entry.id] ? t("flatPanel.tabChanged", { name: entry.label }) : undefined} data-changed={changed[entry.id] ? "" : undefined}
      onClick={() => chooseTab(entry.id)} data-flat-panel-tab={entry.id}
      onKeyDown={event => {
        const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
        if (!step) return;
        event.preventDefault();
        const at = tabs.findIndex(item => item.id === entry.id), next = tabs[(at + step + tabs.length) % tabs.length];
        chooseTab(next.id);
        requestAnimationFrame(() => head.current?.querySelector(`[data-flat-panel-tab="${CSS.escape(next.id)}"]`)?.focus());
      }}
      className={cn(TAB_CLASS, on ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground")}>
      {tabName(entry, on)}
    </button>;
  };
  // The tabs' row: the tabs that fit, ⋯ for the rest, then the search's icon (where a tab is searchable and the
  // search is shut). A hidden ruler beside it measures every tab.
  // The tabs stand at the row's left, ⋯ at its right, beside the search's icon: the room left over is between them.
  const tabRow = single ? null : <div ref={row} className="relative flex min-w-0 flex-1 items-center gap-1" data-flat-panel-tab-row="">
    <div role="tablist" aria-label={label} className="flex min-w-0 flex-1 items-center overflow-hidden" style={{ gap: TAB_GAP_PX }} data-flat-panel-tabs="">
      {visible.map(id => tabs.find(entry => entry.id === id)).filter(Boolean).map(tabButton)}
    </div>
      {hiddenTabs.length ? <DropdownMenu modal={false}>
        <DropdownMenuTrigger asChild>
          <button type="button" aria-label={t("flatPanel.moreTabs")} className={cn(ICON_BUTTON_CLASS, "relative")} data-flat-panel-more=""
            data-changed={hiddenTabs.some(entry => changed[entry.id]) ? "" : undefined}>
            <MoreHorizontal aria-hidden="true" />{hiddenTabs.some(entry => changed[entry.id]) ? <ChangedDot /> : null}
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" sideOffset={4} collisionPadding={8} className={cn(FLOATING_SURFACE_CLASS, "min-w-40")} aria-label={t("flatPanel.moreTabs")}
          data-flat-panel-more-menu="">
          {hiddenTabs.map(entry => {
            const Icon = entry.icon || TAB_ICONS[entry.id];
            const count = countOf(entry.id);
            return <DropdownMenuItem key={entry.id} onSelect={() => chooseTab(entry.id)} data-flat-panel-more-tab={entry.id}
              aria-label={changed[entry.id] ? t("flatPanel.tabChanged", { name: entry.label }) : undefined} data-changed={changed[entry.id] ? "" : undefined}>
              {Icon ? <Icon className="size-4" /> : <span className="size-4 shrink-0" aria-hidden="true" />}
              <span className="relative flex-1"><span className="relative">{entry.label}{changed[entry.id] ? <ChangedDot className="-right-[5px] -top-px" /> : null}</span></span>
              {count !== null ? <span className="tabular-nums text-muted-foreground" data-flat-panel-tab-count="">{count}</span> : null}
            </DropdownMenuItem>;
          })}
        </DropdownMenuContent>
      </DropdownMenu> : null}
    {/* Every tab as the row draws it, unseen, for its width. */}
    <div ref={ruler} aria-hidden="true" className="pointer-events-none invisible absolute left-0 top-0 flex items-center" style={{ gap: TAB_GAP_PX }}>
      {tabs.map(entry => <span key={entry.id} data-tab-ruler={entry.id} className={cn(TAB_CLASS, "font-normal")}>{tabName(entry, entry.id === active, true)}</span>)}
      <span data-more-ruler="" className={ICON_BUTTON_CLASS} />
    </div>
  </div>;
  const searchButton = searchable.size && !searchOpen ? <button type="button" aria-label={searchLabel} className={ICON_BUTTON_CLASS} onClick={openSearch}
    data-flat-panel-search-open=""><Search aria-hidden="true" /></button> : null;
  const searchBox = searchOpen ? <TreeFilterInput label={searchLabel} placeholder={t("flatPanel.searchPlaceholder")} value={query} onChange={setQuery} onKeyDown={onSearchKeyDown}
    inputRef={input} dense onDismiss={closeSearch} dismissLabel={t("flatPanel.closeSearch")} className="min-w-0 flex-1 px-0 shadow-none" data-flat-panel-search=""
    style={SEARCH_BOX_HANG} /> : null;
  const activeCount = searching && searchable.has(active) ? counts[active] : null;
  const aside = <PanelSurface mode={page ? "page" : "push"} label={label} open={open} hidden={hidden} peek={peek} asideRef={surfaceRef} {...surfaceProps}
    width={drawnWidth} grip={page ? null : grip} gripLabel={t("flatPanel.resize")} onKeyDown={onPanelKeyDown} data-flat-panel={mode} headRule={!single || searchOpen} headCompact={compactHead}
    headStack={searchOpen && !single} headRef={head} headInsets={HEAD_INSETS} headProps={{ "data-flat-panel-head": "", "data-searching": searchOpen ? "" : undefined }} scrollerRef={scroller}
    scrollerProps={{ "data-flat-panel-scroller": "" }}
    head={<>
    {/* The head, one row as Figma's Layers panel's, the same on a phone: the tabs (or one tab's title) across its
        width, ⋯ where some do not fit, and the search's icon at its right end; its rule 8px under it (none under one
        tab's title). With the search open the row is its box, the X in the icon's place, and the tabs stand under it. */}
      {searchOpen && !single ? <div className="flex h-7 items-center">{searchBox}</div> : null}
      {searchOpen && single ? searchBox : null}
      {single && !searchOpen ? <h2 id={ids_(single.id).tab} className="flex h-7 min-w-0 flex-1 items-center truncate px-2 text-ui font-medium text-foreground" data-flat-panel-heading=""
        aria-label={changed[single.id] ? t("flatPanel.tabChanged", { name: single.label }) : undefined} data-changed={changed[single.id] ? "" : undefined}>
        <span className="relative min-w-0 truncate">{single.label}{changed[single.id] ? <ChangedDot className="-right-[5px] -top-px" /> : null}</span></h2> : null}
      {!single ? <div className="flex min-w-0 flex-1 items-center gap-1">
        {tabRow}
        {searchButton}
      </div> : searchButton}
    </>}>
      <FlatPanelContext.Provider value={panel}>
        <div ref={body} className={cn("group/body flex flex-col px-(--panel-inset) py-2", compactHead && "pt-1")} data-flat-panel-body="">
          {sections ? <ToolStackContext.Provider value={tabbed}>{sections}</ToolStackContext.Provider> : tabs.map(entry => {
            const shown = entry.id === active;
            return <section key={entry.id} role="tabpanel" id={ids_(entry.id).panel} aria-label={entry.label}
              aria-labelledby={ids_(entry.id).tab} hidden={!shown} data-flat-panel-section={entry.id}>
              <FlatPanelTab panel={panel} id={entry.id} shown={shown}>{entry.content}</FlatPanelTab>
            </section>;
          })}
          {activeCount === 0 ? <p className="py-6 text-center text-muted-foreground" data-flat-panel-empty="">{t("flatPanel.nothingMatches", { query: query.trim() })}</p> : null}
        </div>
      </FlatPanelContext.Provider>
  </PanelSurface>;
  return aside;
}

/** A tab's pill's padding either side of its name, Figma's (`px-2` in `TAB_CLASS`, and the one tab's title's). */
const TAB_PAD_PX = 8;
/** The room between two tabs of the head's row: with the pills' padding, 20px between two names. */
const TAB_GAP_PX = 4;
/** How far the head's boxes hang out past the panel's inset (`--panel-inset`), so what they hold stands on it: a tab's
 * pill (and the one tab's title in its place) by its own padding (`TAB_PAD_PX`, as a selected row's fill hangs 8px), the
 * icon buttons at the row's end (⋯, the search) by theirs (a 14px glyph in a 28px button: 7px). */
const HEAD_INSETS = Object.freeze({ start: TAB_PAD_PX, end: 7 });
/** Where the open search box's icon and its X's glyph stand in from its edges (`TreeFilterInput`, dense: its 12px icon
 * 7px in; its X's 12px glyph centred in a 16px button 6px from the right: 8px). */
const SEARCH_INSETS = Object.freeze({ start: 7, end: 8 });
/** The box hangs out past the head's padding by the difference, so its icon starts, and its X ends, on the inset. */
const SEARCH_BOX_HANG = Object.freeze({ marginLeft: HEAD_INSETS.start - SEARCH_INSETS.start, marginRight: HEAD_INSETS.end - SEARCH_INSETS.end });
/** The room between the head row's icons (⋯ and the search) and before them: Tailwind's gap-1. */
const ICON_GAP_PX = 4;
