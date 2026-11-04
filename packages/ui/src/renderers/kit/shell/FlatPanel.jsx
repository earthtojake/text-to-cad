import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { ArrowLeft, PanelLeftClose, PanelLeftOpen } from "lucide-react";
import { useI18n } from "@cad/ui/i18n";
import { useViewerHost } from "../../../host/context.js";
import { ScrollArea } from "@cad/ui/primitives/scroll-area";
import { ToolbarButton } from "@cad/ui/primitives/toolbar-button";
import { TreeFilterInput } from "@cad/ui/primitives/tree-filter";
import { cn } from "@cad/ui/utils";
import { FLOATING_CHROME_SURFACE_CLASS } from "../../../lib/floatingSurface.js";
import { capturePointer, releasePointer } from "../../../lib/pointerCapture.js";
import { STRIP_BUTTON_CLASS, TOUCH_STRIP_BUTTON_CLASS } from "../tools/stripTouch.js";
import { VIEWPORT_INSET_PX } from "./viewportLayout.js";

/**
 * A flat view's panel (a board's, a schematic's: `FlatViewFrame.jsx`), docked at the view's left
 * edge the way KiCad's Appearance panel is: one search box over everything, then text tabs, one per
 * list (a board's Circuit and Layers, a schematic's Circuit and Hierarchy), and the open tab's list
 * under them, scrolling as one.
 *
 * - **The toggle never moves.** Open, it is the first thing in the panel, at its top-left; collapsed,
 *   the panel goes completely and the same button stays on the same pixel, alone on a small pill over
 *   the canvas (`FlatPanelPill`), so a second click undoes the first. ⌘\ (Ctrl+\) does the same, and
 *   / opens the panel on its search.
 * - **Search** is the panel's, not a tab's: while something is typed, the tabs step aside and the
 *   body lists what matches in every tab, each under its tab's name (a tab with no match is left out;
 *   a tab of many ranked hits, `searchLast`, after the others);
 *   Escape or the box's X clears it. A tab reads the query from `useFlatPanel()`, and a tab whose
 *   results the arrow keys walk registers its keys there (the Circuit's).
 * - **Three ways to be shown**, the frame's choice by the view's width: `docked` beside the canvas,
 *   the canvas the narrower for it, its width the person's (a grip on its right edge, kept);
 *   `overlay`, under 1024px, over the canvas, a scrim behind it that closes it, as Escape does;
 *   `page`, on a phone, the whole view, with Back in the toggle's place; a pick in it closes it.
 *
 * Every tab stays mounted, shown or not, so a tree keeps its expansion; each keeps its own scroll.
 */

const PANEL_INSET_PX = VIEWPORT_INSET_PX + 5;
const KEY_NUDGE_PX = 16;
export const FLAT_PANEL_DEFAULT_WIDTH = 248;
export const FLAT_PANEL_MIN_WIDTH = 200;
/** The toggle's key, as its tooltip shows it: ⌘\ on a Mac (the host's `environment.platform`), Ctrl+\ elsewhere. */
export const flatPanelShortcut = platform => (platform === "darwin" ? "⌘\\" : "Ctrl+\\");

const FlatPanelContext = createContext(null);
/**
 * The panel a tab is drawn in: `query` (what is typed, `""` for none), `searching`,
 * `registerKeys(handler)` (the search box's arrow and Enter keys go to `handler`; returns the
 * release) and `picked()` (a row pressed: on a phone, the panel gives the view back). Null outside one.
 */
export const useFlatPanel = () => useContext(FlatPanelContext);

/** The collapsed panel: its toggle alone, on the pixel the open panel's toggle takes. */
export function FlatPanelPill({ onOpen, touch = false }) {
  const { t } = useI18n();
  const platform = useViewerHost()?.environment?.platform;
  return <div className={cn("pointer-events-auto absolute z-20 inline-flex rounded-md p-1", FLOATING_CHROME_SURFACE_CLASS)}
    style={{ top: VIEWPORT_INSET_PX, left: VIEWPORT_INSET_PX }} data-flat-panel-pill="">
    <ToolbarButton label={t("flatPanel.show")} shortcut={touch ? "" : flatPanelShortcut(platform)} tooltipSide="right"
      className={touch ? TOUCH_STRIP_BUTTON_CLASS : STRIP_BUTTON_CLASS} aria-expanded={false} onClick={onOpen} data-flat-panel-toggle="">
      <PanelLeftOpen aria-hidden="true" />
    </ToolbarButton>
  </div>;
}

/**
 * @param {{ mode: "docked" | "overlay" | "page", open: boolean, onClose(): void, label: string,
 *   searchLabel: string, searchPlaceholder: string, tabs: { id: string, label: string, content: import("react").ReactNode, searchLast?: boolean }[],
 *   tab: string, onTabChange(id: string): void, width: number, maxWidth: number, onWidthChange(width: number): void,
 *   focusSearch: number }} props
 *   `focusSearch`: a count; each new value puts the keyboard in the search box (/).
 */
export default function FlatPanel({ mode, open, onClose, label, searchLabel, searchPlaceholder, tabs, tab, onTabChange, width, maxWidth, onWidthChange, focusSearch }) {
  const { t } = useI18n();
  const platform = useViewerHost()?.environment?.platform;
  const page = mode === "page", docked = mode === "docked";
  const [query, setQuery] = useState("");
  const searching = query.trim() !== "";
  const keys = useRef(null);
  const registerKeys = useCallback(handler => {
    keys.current = handler;
    return () => { if (keys.current === handler) keys.current = null; };
  }, []);
  const closeRef = useRef(onClose);
  closeRef.current = onClose;
  const picked = useCallback(() => { if (page) closeRef.current(); }, [page]);
  const panel = useMemo(() => ({ query, searching, registerKeys, picked }), [query, searching, registerKeys, picked]);

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
  useEffect(() => { if (focusSearch && open) input.current?.focus(); }, [focusSearch, open]);
  const onSearchKeyDown = event => {
    if (event.key === "Escape") {
      if (query) { event.preventDefault(); event.stopPropagation(); setQuery(""); return; }
      if (!docked) { event.preventDefault(); event.stopPropagation(); onClose(); }
      return;
    }
    keys.current?.(event);
  };
  // A floating panel (over the canvas, or the whole view) goes with Escape, wherever its focus is.
  const onPanelKeyDown = event => {
    if (docked || event.key !== "Escape" || event.defaultPrevented) return;
    event.preventDefault();
    event.stopPropagation();
    onClose();
  };

  // The width: the person's, from the grip on the right edge (a floating panel's too), one write when it lets go.
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

  const active = tabs.some(entry => entry.id === tab) ? tab : tabs[0]?.id;
  const ids = id => ({ tab: `flat-panel-tab-${id}`, panel: `flat-panel-body-${id}` });
  const aside = <aside aria-label={label} data-flat-panel={mode} data-open={open ? "" : undefined} hidden={!open}
    onKeyDown={onPanelKeyDown}
    className={cn("flex min-h-0 flex-col bg-background text-tiny text-foreground",
      docked && "relative h-full shrink-0 border-r border-border",
      mode === "overlay" && "absolute inset-y-0 left-0 z-40 border-r border-border shadow-xl",
      page && "absolute inset-0 z-50")}
    style={page ? undefined : { width: drawnWidth }}>
    {/* The head: the toggle where the pill's is (Back, on a phone), then the search. */}
    <div className="flex shrink-0 items-center gap-1.5" style={{ padding: `${PANEL_INSET_PX}px ${PANEL_INSET_PX - 4}px 6px ${PANEL_INSET_PX}px` }} data-flat-panel-head="">
      {page
        ? <ToolbarButton label={t("flatPanel.back")} tooltip={false} className={TOUCH_STRIP_BUTTON_CLASS} onClick={onClose} data-flat-panel-toggle=""><ArrowLeft aria-hidden="true" /></ToolbarButton>
        : <ToolbarButton label={t("flatPanel.hide")} shortcut={flatPanelShortcut(platform)} tooltipSide="right" className={STRIP_BUTTON_CLASS} aria-expanded onClick={onClose} data-flat-panel-toggle="">
          <PanelLeftClose aria-hidden="true" />
        </ToolbarButton>}
      <TreeFilterInput label={searchLabel} placeholder={searchPlaceholder} value={query} onChange={setQuery} onKeyDown={onSearchKeyDown}
        inputRef={input} dense className="min-w-0 flex-1 rounded-md border border-border px-0.5 shadow-none" data-flat-panel-search="" />
    </div>
    {/* The tabs, text: KiCad's Appearance panel's. While a search is up they step aside. */}
    <div role="tablist" aria-label={label} hidden={searching} className="flex shrink-0 gap-4 border-b border-border" style={{ paddingLeft: PANEL_INSET_PX + 2, paddingRight: PANEL_INSET_PX }}>
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
          className={cn("-mb-px border-b-2 py-1.5 text-tiny transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/45",
            on ? "border-foreground text-foreground" : "border-transparent text-muted-foreground hover:text-foreground")}>
          {entry.label}
        </button>;
      })}
    </div>
    <ScrollArea className="min-h-0 flex-1" viewportRef={scroller} viewportProps={{ "data-flat-panel-scroller": "" }}>
      <FlatPanelContext.Provider value={panel}>
        <div className={cn("group/body flex flex-col pb-2", searching && "pt-1")} data-flat-panel-body="">
          {tabs.map(entry => {
            const shown = searching || entry.id === active;
            return <section key={entry.id} role="tabpanel" id={ids(entry.id).panel} aria-labelledby={ids(entry.id).tab} hidden={!shown}
              data-flat-panel-section={entry.id}
              // Searching, a long ranked list (the Circuit's) goes under the short ones, so a layer or a sheet found is not under 200 parts.
              style={searching && entry.searchLast ? { order: 1 } : undefined}
              // Searching, a tab with nothing found is left out, and its name with it.
              className={cn(searching && "not-has-[[data-flat-panel-hit]]:hidden")}>
              {searching ? <h3 className="flex h-6 items-center text-tiny text-muted-foreground" style={{ paddingLeft: PANEL_INSET_PX - 1 }}>{entry.label}</h3> : null}
              {entry.content}
            </section>;
          })}
          {searching ? <p style={{ order: 2 }} className="px-3 py-6 text-center text-muted-foreground group-has-[[data-flat-panel-hit]]/body:hidden"
            data-flat-panel-empty="">{t("flatPanel.nothingMatches", { query: query.trim() })}</p> : null}
        </div>
      </FlatPanelContext.Provider>
    </ScrollArea>
    {page ? null : <div role="separator" aria-orientation="vertical" aria-label={t("flatPanel.resize")} aria-valuenow={drawnWidth}
      aria-valuemin={FLAT_PANEL_MIN_WIDTH} aria-valuemax={maxWidth} tabIndex={0}
      className={cn("absolute inset-y-0 -right-1 z-10 w-2 cursor-col-resize touch-none focus-visible:outline-none",
        "after:absolute after:inset-y-0 after:left-1/2 after:w-px after:-translate-x-1/2 after:transition-colors hover:after:bg-ring focus-visible:after:bg-ring",
        draft !== null && "after:bg-ring")}
      onPointerDown={startDrag} onPointerMove={moveDrag} onPointerUp={stopDrag} onPointerCancel={stopDrag} onKeyDown={keyDrag} data-flat-panel-grip="" />}
  </aside>;
  return <>
    {/* Over the canvas, a scrim that closes the panel; nothing behind a docked one or the phone's page. */}
    {mode === "overlay" && open ? <div className="absolute inset-0 z-30 bg-black/20" aria-hidden="true" onPointerDown={event => { event.preventDefault(); onClose(); }} data-flat-panel-scrim="" /> : null}
    {aside}
  </>;
}
