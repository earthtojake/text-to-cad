import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useI18n } from "@cad/ui/i18n";
import { ViewerHostContext } from "../../../host/context.js";
import { ScrollArea } from "@cad/ui/primitives/scroll-area";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { TreeFilterInput } from "@cad/ui/primitives/tree-filter";
import { cn } from "@cad/ui/utils";
import { FLOATING_CHROME_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { capturePointer, releasePointer } from "../../../lib/pointerCapture.js";
import { STRIP_BUTTON_CLASS, TOUCH_STRIP_BUTTON_CLASS } from "../tools/stripTouch.js";
import { ToolStackContext } from "../tools/ToolStack.jsx";
import { FLAT_DETAIL_MIN_HEIGHT, flatDetailHeight } from "../tools/toolStackLayout.js";
import { FilePanelContext, hasLegacyFilePanel, legacyFilePanel, legacyFilePanelTab, readFilePanel, withoutLegacyFilePanel } from "../../../file-viewer/filePanel.js";
import { VIEWPORT_INSET_PX } from "./viewportLayout.js";

/**
 * A flat view's panel (a board's, a schematic's: `FlatViewFrame.jsx`), docked at the view's left
 * edge the way KiCad's Appearance panel is: one search box over everything, its collapse button
 * after it, then a row of tabs, buttons as Figma's (a board's Parts, Nets and Layers, a schematic's
 * Parts, Nets and Hierarchy), and the open tab's list under them, scrolling as one; under that, when the
 * view hands one in, what is picked in detail (`detail`: the Selected pane, `kit/inspector/ItemDetail.jsx`),
 * 40% of the panel's height whatever is picked, until the person sizes it, and scrolling on its own, whatever tab is open. It keeps two lines,
 * the same on both sides: its boxes 8px in, what is read in them 16px in.
 *
 * - **Collapsed, it goes completely**: its expand button alone on a small pill at the canvas's
 *   top-left (`FlatPanelPill`). ⌘\ (Ctrl+\) shows and hides it, and / opens it on its search.
 * - **Search** is the panel's, not a tab's: while something is typed, the tabs step aside and the
 *   body lists what matches in every tab, each under its tab's name (a tab with no match is left out;
 *   a tab of many ranked hits, `searchLast`, after the others);
 *   Escape or the box's X clears it. A tab reads the query from `useFlatPanel()`, and a tab whose
 *   results the arrow keys walk registers its keys there (the Parts' and the Nets'): the open tab's get them.
 * - **Two ways to be shown**: `docked` beside the canvas, the canvas always the narrower for it, its
 *   width the person's (a grip on its right edge, kept); `page`, on a phone, the whole view, with
 *   Back before its search; a pick in it closes it.
 *
 * Every tab stays mounted, shown or not, so a tree keeps its expansion; each keeps its own scroll.
 *
 * Its tabs are handed in (`tabs`, a board's and a schematic's), or are the sections drawn in it
 * (`sections`: a 3D view's `ToolPanel`s — its Model tree or Links, Position and the rest — each a tab by its
 * name, in their order, `ToolPanel.jsx`'s tabbed form). `useFlatPanelState` is what a view keeps of it.
 */

// Narrower than this, a file's panel starts collapsed (GitHub's file tree's breakpoint); opened, it docks all the same.
export const FLAT_PANEL_OPEN_PX = 1024;

/**
 * A view's panel's state, the same in every view that has one, and the file's (`filePanel.js`): kept
 * in the file's view as its camera is, so a reload brings it back for that file and another file
 * starts at its own. Docked (a phone: the whole view); open as a file first opens in a view 1024px wide
 * or more and collapsed in a narrower one, until the person opens or closes it — that choice is then
 * the file's, at any width; its width (216px at first), its tab (the first at first) and the Selected
 * pane's height (`flatDetailHeight`'s) the person's too. On a phone it starts collapsed each time and
 * keeps nothing. `control` is what ⌘\ and / reach (`toggle()`, `search()`).
 *
 * A file with no panel of its own starts from the tab's old shared one, where the tab still carries it
 * (`legacyFilePanel`), which is then dropped from the tab's settings and never written there again; a
 * `compact` view (a picture taken out of sight, a host's inline card) only reads it, as its panel is
 * never shown and its file's view is not the one kept.
 * @param {{ frameRef: { current: HTMLElement | null }, mobile: boolean, enabled: boolean, kind: string,
 *   toolStack: object, onToolStackChange(patch: (layout: object) => object): void, compact?: boolean,
 *   reach?: number | null }} options
 *   `reach`: where the strip starts, px from the view's left edge (`ViewFrame.jsx` measures it): the panel
 *   is at most as wide as leaves its head an inset clear of the strip, and never wider than half the view.
 */
export function useFlatPanelState({ frameRef, mobile, enabled, kind, toolStack, onToolStackChange, compact = false, reach = null }) {
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
  const mode = mobile ? "page" : "docked";
  // A phone's panel is the view's own while it is open, and kept nowhere.
  const [pageOpen, setPageOpen] = useState(false);
  useEffect(() => { setPageOpen(false); }, [mode]);
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
  const wide = !(frameWidth && frameWidth < FLAT_PANEL_OPEN_PX);
  const open = enabled && (mode === "page" ? pageOpen : (panel.open ?? wide));
  const setOpen = useCallback(next => {
    if (mode === "page") { setPageOpen(next); return; }
    change({ open: Boolean(next) });
  }, [mode, change]);
  const tab = panel.tab;
  const changeTab = useCallback(id => change({ tab: id }), [change]);
  // A tab brought up by what the person did elsewhere (a menu item of the viewport's): open, on it.
  const showTab = useCallback(id => { changeTab(id); setOpen(true); }, [changeTab, setOpen]);
  const half = Math.floor((frameWidth || 2 * FLAT_PANEL_DEFAULT_WIDTH) / 2);
  const maxWidth = Math.max(FLAT_PANEL_MIN_WIDTH, Math.min(half, reach > 0 ? reach - VIEWPORT_INSET_PX : half));
  const width = panel.width ?? FLAT_PANEL_DEFAULT_WIDTH;
  const changeWidth = useCallback(next => change({ width: next }), [change]);
  const detailHeight = panel.detailHeight ?? null;
  const changeDetailHeight = useCallback(next => change({ detailHeight: next }), [change]);
  const [focusSearch, setFocusSearch] = useState(0);
  const openRef = useRef(open);
  openRef.current = open;
  const control = enabled ? {
    toggle: () => setOpen(!openRef.current),
    search: () => { setOpen(true); setFocusSearch(count => count + 1); return true; }
  } : null;
  return { mode, open, setOpen, tab, changeTab, showTab, width, maxWidth, changeWidth, detailHeight, changeDetailHeight, focusSearch, control };
}

// The panel's two lines, the same on both sides (Figma's): every box in its head and lists — the search
// field, the collapse button, a tab's button, a row's background — runs 8px from each edge
// (`SURFACE_PX`: the head's padding, and the body's and the detail's, so no tab or list pads itself),
// and what is read in them starts on the line 16px in: the search icon, a tab's name, a row's first
// glyph (`--tree-row-pad`, the row's 8px inside the body's), a heading, a settings label; at the
// right a row's last action's glyph ends 16px in (`--tree-row-actions-pad`).
const SURFACE_PX = 8;
const PANEL_ROW_VARIABLES = { "--tree-row-pad": `${SURFACE_PX}px`, "--tree-row-actions-pad": "6px" };
const KEY_NUDGE_PX = 16;
export const FLAT_PANEL_DEFAULT_WIDTH = 216;
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
  return panel.shown !== false && (!stack?.tabbed || stack.searching || stack.activeSection === id);
}

// A tab's own view of the panel: its keys registered under its id, and whether it is on screen.
function FlatPanelTab({ panel, id, shown, children }) {
  const { registerKeys } = panel;
  const value = useMemo(() => ({ ...panel, shown: panel.shown && shown, registerKeys: handler => registerKeys(handler, id) }), [panel, id, shown, registerKeys]);
  return <FlatPanelContext.Provider value={value}>{children}</FlatPanelContext.Provider>;
}

/** The collapsed panel: its expand button alone, at the canvas's top-left. */
export function FlatPanelPill({ onOpen, touch = false }) {
  const { t } = useI18n();
  const platform = useContext(ViewerHostContext)?.environment?.platform;
  return <div className={cn("pointer-events-auto absolute z-20 inline-flex rounded-md p-1", FLOATING_CHROME_SURFACE_CLASS)}
    style={{ top: VIEWPORT_INSET_PX, left: VIEWPORT_INSET_PX }} data-flat-panel-pill="">
    <ToolbarButton label={t("flatPanel.show")} shortcut={touch ? "" : flatPanelShortcut(platform)} tooltipSide="right"
      className={touch ? TOUCH_STRIP_BUTTON_CLASS : STRIP_BUTTON_CLASS} aria-expanded={false} onClick={onOpen} data-flat-panel-toggle="">
      <PanelLeftOpen aria-hidden="true" />
    </ToolbarButton>
  </div>;
}

/**
 * @param {{ mode: "docked" | "page", open: boolean, onClose(): void, label: string,
 *   searchLabel: string, tabs: { id: string, label: string, content: import("react").ReactNode, searchLast?: boolean }[],
 *   tab: string, onTabChange(id: string): void, width: number, maxWidth: number, onWidthChange(width: number): void,
 *   focusSearch: number, detail?: import("react").ReactNode }} props
 *   `focusSearch`: a count; each new value puts the keyboard in the search box (/). `detail`: what is picked, under the lists.
 *   `onShowTab`: what a section's `open` (`ToolStackContext`) brings its tab up by.
 */
export default function FlatPanel({ mode, open, onClose, label, searchLabel, tabs: given = null, sections = null, tab, onTabChange, onShowTab = null, width, maxWidth, onWidthChange, focusSearch, detail = null, hidden = false,
  detailHeight = null, onDetailHeightChange = null }) {
  const { t } = useI18n();
  const platform = useContext(ViewerHostContext)?.environment?.platform;
  const page = mode === "page", docked = mode === "docked";
  const [query, setQuery] = useState("");
  const searching = query.trim() !== "";
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
  const panel = useMemo(() => ({ query, searching, page, shown: onScreen, registerKeys, picked }), [query, searching, page, onScreen, registerKeys, picked]);

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

  // Each tab keeps its own scroll, and the search its own: the body is one scroller.
  const scroller = useRef(null), scrolls = useRef(new Map());
  const shownKey = searching ? "\u0000search" : tab;
  const lastKey = useRef(shownKey);
  useLayoutEffect(() => {
    const element = scroller.current;
    if (!element || lastKey.current === shownKey) return;
    scrolls.current.set(lastKey.current, element.scrollTop);
    lastKey.current = shownKey;
    element.scrollTop = scrolls.current.get(shownKey) ?? 0;
  }, [shownKey]);

  const input = useRef(null);
  // Each new count once, when the panel is open: a reopened or remounted panel takes no focus.
  const searched = useRef(focusSearch);
  useEffect(() => {
    if (!open || focusSearch === searched.current) return;
    searched.current = focusSearch;
    input.current?.focus();
  }, [focusSearch, open]);
  const onSearchKeyDown = event => {
    if (event.key === "Escape") {
      if (query) { event.preventDefault(); event.stopPropagation(); setQuery(""); return; }
      if (page) { event.preventDefault(); event.stopPropagation(); onClose(); }
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

  // The width: the person's, from the grip on the right edge, one write when it lets go.
  const [draft, setDraft] = useState(null);
  const drawnWidth = Math.min(maxWidth, Math.max(FLAT_PANEL_MIN_WIDTH, draft ?? width));
  const drag = useRef(null);
  const clamp = value => Math.round(Math.min(maxWidth, Math.max(FLAT_PANEL_MIN_WIDTH, value)));
  const startDrag = event => {
    if (event.button !== 0) return;
    event.preventDefault();
    drag.current = { pointerId: event.pointerId, x: event.clientX, from: drawnWidth, next: null };
    capturePointer(event.currentTarget, event.pointerId);
  };
  const moveDrag = event => {
    const current = drag.current;
    if (current?.pointerId !== event.pointerId) return;
    current.next = clamp(current.from + event.clientX - current.x);
    setDraft(current.next);
  };
  const stopDrag = event => {
    const current = drag.current;
    if (!current || current.pointerId !== event.pointerId) return;
    drag.current = null;
    releasePointer(event.currentTarget, event.pointerId);
    setDraft(null);
    if (current.next !== null && current.next !== width) onWidthChange(current.next);
  };
  const keyDrag = event => {
    const next = { ArrowLeft: drawnWidth - KEY_NUDGE_PX, ArrowRight: drawnWidth + KEY_NUDGE_PX, Home: 0, End: Infinity }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    onWidthChange(clamp(next));
  };

  // The detail's height: the person's from the grip on its top edge (one write when it lets go; a
  // double-click on it clears that), else its steady share of the panel (`flatDetailHeight`).
  const asideRef = useRef(null);
  const [asideHeight, setAsideHeight] = useState(0);
  useLayoutEffect(() => {
    const element = asideRef.current;
    if (!element || typeof ResizeObserver === "undefined") return undefined;
    const measure = () => setAsideHeight(Math.round(element.getBoundingClientRect().height));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  const [detailDraft, setDetailDraft] = useState(null);
  const { height: drawnDetail, max: detailMax } = flatDetailHeight({ panelHeight: asideHeight, kept: detailHeight, draft: detailDraft });
  const clampDetail = value => flatDetailHeight({ panelHeight: asideHeight, draft: value }).height;
  const detailDrag = useRef(null);
  const startDetailDrag = event => {
    if (event.button !== 0) return;
    event.preventDefault();
    detailDrag.current = { pointerId: event.pointerId, y: event.clientY, from: drawnDetail, next: null };
    capturePointer(event.currentTarget, event.pointerId);
  };
  const moveDetailDrag = event => {
    const current = detailDrag.current;
    if (current?.pointerId !== event.pointerId) return;
    current.next = clampDetail(current.from - (event.clientY - current.y));
    setDetailDraft(current.next);
  };
  const stopDetailDrag = event => {
    const current = detailDrag.current;
    if (!current || current.pointerId !== event.pointerId) return;
    detailDrag.current = null;
    releasePointer(event.currentTarget, event.pointerId);
    setDetailDraft(null);
    if (current.next !== null && current.next !== detailHeight) onDetailHeightChange?.(current.next);
  };
  const keyDetailDrag = event => {
    const next = { ArrowUp: drawnDetail + KEY_NUDGE_PX, ArrowDown: drawnDetail - KEY_NUDGE_PX, Home: Infinity, End: 0 }[event.key];
    if (next === undefined) return;
    event.preventDefault();
    onDetailHeightChange?.(clampDetail(next));
  };

  const active = tabs.some(entry => entry.id === tab) ? tab : tabs[0]?.id;
  const activeRef = useRef(active);
  activeRef.current = active;
  // One tab is no choice: no row of tabs, and no name over its hits; its list says what it is by its own label.
  const single = tabs.length <= 1;
  const tabbed = useMemo(() => ({ tabbed: true, single, activeSection: active, searching, register, open: onShowTab }), [single, active, searching, register, onShowTab]);
  const ids = id => ({ tab: `flat-panel-tab-${id}`, panel: `flat-panel-body-${id}` });
  const aside = <aside ref={asideRef} aria-label={label} data-flat-panel={mode} data-open={open ? "" : undefined} hidden={!open || hidden}
    onKeyDown={onPanelKeyDown}
    // The chrome's colour, the navbar's: a step off the canvas, so the frame reads apart from the picture.
    className={cn("flex min-h-0 flex-col bg-sidebar text-tiny text-foreground",
      docked && "relative h-full shrink-0 border-r border-border",
      page && "absolute inset-0 z-50")}
    style={page ? PANEL_ROW_VARIABLES : { ...PANEL_ROW_VARIABLES, width: drawnWidth }}>
    {/* The head: the search, then the collapse button at its right (Back before it, on a phone). */}
    <div className="flex shrink-0 items-center gap-1.5" style={{ padding: `${SURFACE_PX}px ${SURFACE_PX}px 6px` }} data-flat-panel-head="">
      {page ? <ToolbarButton label={t("flatPanel.back")} tooltip={false} className={TOUCH_STRIP_BUTTON_CLASS} onClick={onClose} data-flat-panel-toggle=""><ArrowLeft aria-hidden="true" /></ToolbarButton> : null}
      <TreeFilterInput label={searchLabel} placeholder={t("flatPanel.searchPlaceholder")} value={query} onChange={setQuery} onKeyDown={onSearchKeyDown}
        inputRef={input} dense className="min-w-0 flex-1 rounded-md border border-border pl-px pr-0.5 shadow-none" data-flat-panel-search="" />
      {page ? null : <ToolbarButton label={t("flatPanel.hide")} shortcut={flatPanelShortcut(platform)} tooltipSide="bottom" className={STRIP_BUTTON_CLASS} aria-expanded onClick={onClose} data-flat-panel-toggle="">
        <PanelLeftClose aria-hidden="true" />
      </ToolbarButton>}
    </div>
    {/* The tabs, buttons as Figma's: the open one raised on the accent, their rule under them. While a
        search is up they step aside; a panel of one tab has none, and no rule: its list starts under the
        head's 6px. */}
    <div role="tablist" aria-label={label} hidden={searching || single} className="flex shrink-0 items-center gap-1 border-b border-border" style={{ padding: `0 ${SURFACE_PX}px ${SURFACE_PX}px` }}>
      {tabs.map(entry => {
        const on = entry.id === active;
        return <button key={entry.id} type="button" role="tab" id={ids(entry.id).tab} aria-controls={ids(entry.id).panel} aria-selected={on} tabIndex={on ? 0 : -1}
          onClick={() => onTabChange(entry.id)} data-flat-panel-tab={entry.id}
          onKeyDown={event => {
            const step = { ArrowRight: 1, ArrowLeft: -1 }[event.key];
            if (!step) return;
            event.preventDefault();
            const at = tabs.findIndex(item => item.id === entry.id), next = tabs[(at + step + tabs.length) % tabs.length];
            onTabChange(next.id);
            event.currentTarget.parentElement?.querySelector(`[data-flat-panel-tab="${CSS.escape(next.id)}"]`)?.focus();
          }}
          className={cn("h-6 rounded-md px-2 text-tiny transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45",
            on ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent/50 hover:text-foreground")}>
          {/* The open tab's name is medium weight; every tab is as wide as its name in that weight (an
              unseen copy holds it), so choosing one moves nothing. */}
          <span className="grid justify-items-center">
            <span aria-hidden="true" className="invisible col-start-1 row-start-1 font-medium">{entry.label}</span>
            <span className={cn("col-start-1 row-start-1", on && "font-medium")} data-flat-panel-tab-name="">{entry.label}</span>
          </span>
        </button>;
      })}
    </div>
    <ScrollArea className="min-h-0 flex-1" viewportRef={scroller} viewportProps={{ "data-flat-panel-scroller": "" }}>
      <FlatPanelContext.Provider value={panel}>
        <div ref={body} className={cn("group/body flex flex-col px-2 pb-2", single ? "pt-0" : "pt-1")} data-flat-panel-body="">
          {sections ? <ToolStackContext.Provider value={tabbed}>{sections}</ToolStackContext.Provider> : tabs.map(entry => {
            const shown = searching || entry.id === active;
            return <section key={entry.id} role={single ? "region" : "tabpanel"} id={ids(entry.id).panel} aria-label={entry.label}
              aria-labelledby={single ? undefined : ids(entry.id).tab} hidden={!shown} data-flat-panel-section={entry.id}
              // Searching, a long ranked list (the Parts', the Nets') goes under the short ones, so a layer or a sheet found is not under 200 parts.
              style={searching && entry.searchLast ? { order: 1 } : undefined}
              // Searching, a tab with nothing found is left out, and its name with it.
              className={cn(searching && "not-has-[[data-flat-panel-hit]]:hidden")}>
              {searching && !single ? <h3 className="flex h-6 items-center px-2 text-tiny text-muted-foreground">{entry.label}</h3> : null}
              <FlatPanelTab panel={panel} id={entry.id} shown={shown}>{entry.content}</FlatPanelTab>
            </section>;
          })}
          {searching ? <p style={{ order: 2 }} className="px-3 py-6 text-center text-muted-foreground group-has-[[data-flat-panel-hit]]/body:hidden"
            data-flat-panel-empty="">{t("flatPanel.nothingMatches", { query: query.trim() })}</p> : null}
        </div>
      </FlatPanelContext.Provider>
    </ScrollArea>
    {/* What is picked, in detail (a part's pads, a net's): under the lists, whatever tab is open, at
        the person's height, scrolling on its own; its top edge is the grip that sizes it. */}
    {detail ? <div className="relative flex min-h-0 shrink-0 flex-col border-t border-border" style={{ height: drawnDetail }} data-flat-panel-detail="">
      <div role="separator" aria-orientation="horizontal" aria-label={t("flatPanel.resizeDetail")} aria-description={t("flatPanel.resizeDetailHint")} aria-valuenow={drawnDetail}
        aria-valuemin={FLAT_DETAIL_MIN_HEIGHT} aria-valuemax={detailMax} tabIndex={0}
        className={cn("absolute inset-x-0 -top-1 z-10 h-2 cursor-row-resize touch-none focus-visible:outline-none",
          "after:absolute after:inset-x-0 after:top-1/2 after:h-px after:-translate-y-1/2 after:transition-colors hover:after:bg-ring focus-visible:after:bg-ring",
          detailDraft !== null && "after:bg-ring")}
        onPointerDown={startDetailDrag} onPointerMove={moveDetailDrag} onPointerUp={stopDetailDrag} onPointerCancel={stopDetailDrag} onKeyDown={keyDetailDrag}
        onDoubleClick={() => { if (detailHeight !== null) onDetailHeightChange?.(undefined); }}
        data-flat-panel-detail-grip="" />
      <ScrollArea className="min-h-0 flex-1">
        <div className="px-2"><FlatPanelContext.Provider value={panel}>{detail}</FlatPanelContext.Provider></div>
      </ScrollArea>
    </div> : null}
    {page ? null : <div role="separator" aria-orientation="vertical" aria-label={t("flatPanel.resize")} aria-valuenow={drawnWidth}
      aria-valuemin={FLAT_PANEL_MIN_WIDTH} aria-valuemax={maxWidth} tabIndex={0}
      className={cn("absolute inset-y-0 -right-1 z-10 w-2 cursor-col-resize touch-none focus-visible:outline-none",
        "after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2 after:transition-colors hover:after:bg-ring focus-visible:after:bg-ring",
        draft !== null && "after:bg-ring")}
      onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={stopDrag} onPointerCancel={stopDrag} onKeyDown={keyDrag} data-flat-panel-grip="" />}
  </aside>;
  return aside;
}
