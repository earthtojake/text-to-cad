import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";
import { readFilePanel } from "../file-viewer/filePanel.js";
import { PanelFoot } from "../file-viewer/PanelFoot.jsx";
import { PanelSheet, usePanelFrame } from "../file-viewer/panelFrame.jsx";
import { PanelSurface, usePanelWidth } from "../file-viewer/PanelSurface.jsx";
import { MAX_PANEL_WIDTH, MIN_PANEL_WIDTH, clampPanelWidth } from "../file-viewer/panelToggles.js";
import { useViewerMobile } from "../file-viewer/responsive.js";
import { TreeRowsLoading } from "../primitives/tree-row.jsx";
import { useI18n } from "../i18n/index.js";
import { useAppMenu } from "../file-viewer/navbarSlots.js";
import { PlacesList, placesClass } from "./LibraryPlaces.jsx";

// The home's sidebar (`ModelLibrary.tsx`): its places, over the panel's foot (`file-viewer/PanelFoot.jsx`: the host's
// links and Settings, the same foot a document's panel ends in). It is the viewer's panel over another
// page: the same frame (`file-viewer/panelFrame.jsx`), the same surface, grip and peek card
// (`file-viewer/PanelSurface.jsx`), the same toggle in the navbar and the same key, so a person who knows a document's
// panel knows this one. Only what it holds is the home's.

/**
 * @typedef {{ open?: boolean, width?: number }} SidebarRecord  What is kept of the sidebar, each absent until the
 *   person sets it (`file-viewer/filePanel.js`'s `open` and `width`, the home's in place of a file's): they opened
 *   (`true`) or closed (`false`) it, which then holds at any width; the width they dragged it to.
 */

/** Whether a key press is the panel's: \ with ⌘ or Ctrl, and nothing else held (a view's frame reads the same chord). */
const isPanelKey = event => (event.code === "Backslash" || event.key === "\\") && (event.metaKey || event.ctrlKey) && !event.altKey && !event.shiftKey;

/**
 * The home's frame under its navbar: the sidebar at the left, and the place on screen (`children`) in the room it
 * leaves. The sidebar behaves as a document's panel does:
 *
 * - Pinned, it pushes the page; collapsed, it leaves nothing. Its toggle is the navbar's, after the logo, said from the
 *   home's first paint; ⌘\ (Ctrl+\) does what the toggle does, outside a text field.
 * - Until the person opens or closes it, the home's width decides (open where the page keeps 640px beside the
 *   default 232px), again at every resize; after, their choice holds at any width.
 * - Collapsed, a mouse resting on the toggle peeks it as a card over the page, never kept: Escape, a press on the page
 *   or the pointer leaving put it away, and only the toggle or its key pins it.
 * - Its width is the person's by the grip on its right edge: 232px at first, 200 to 480.
 * - On a phone it is a sheet from the left under the navbar; a place chosen in it closes it.
 *
 * What is kept is the person's choice and their width (`SidebarRecord`): the home starts from what the host kept
 * (`panel`, read as it mounts) and hands each change back whole (`onPanelChange`: the tab's settings); without a host
 * that keeps it, it lasts as long as the home is mounted. A peek, the phone's sheet and what the width does are never kept.
 * It ends in the panel's foot (`PanelFoot`: the host's links and Settings), as a document's panel does.
 *
 * `places` null is the home before anything of it is known (a page's frame drawn before its app takes over): the same
 * sidebar, open or shut and as wide as it will be, placeholder rows where its places will stand.
 *
 * @param {{ places: import("./LibraryPlaces.jsx").PlacesProps | null, panel?: SidebarRecord | null,
 *   onPanelChange?: ((panel: SidebarRecord) => void) | null, children?: import("react").ReactNode }} props
 */
export function LibraryFrame({ places, panel = null, onPanelChange = null, children }) {
  const { t } = useI18n();
  const mobile = useViewerMobile();
  // The home's width, which opens or collapses the sidebar until the person chooses (0 until measured).
  const [element, setElement] = useState(null);
  const [frameWidth, setFrameWidth] = useState(0);
  useLayoutEffect(() => {
    if (!element) return undefined;
    const measure = () => setFrameWidth(Math.round(element.getBoundingClientRect().width));
    measure();
    if (typeof ResizeObserver === "undefined") return undefined;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [element]);
  // What is kept, as a file's panel is (`renderers/kit/shell/FlatPanel.jsx`'s `useFlatPanelState`): the sidebar as the
  // host kept it when the home came up, then each change the person makes, written through whole. Only a choice is written.
  const [record, setRecord] = useState(() => readFilePanel(panel));
  const latest = useRef({ record, onPanelChange });
  latest.current = { record, onPanelChange };
  const change = useCallback(patch => {
    const { open, width } = { ...latest.current.record, ...patch };
    const next = { ...(typeof open === "boolean" ? { open } : null), ...(width ? { width } : null) };
    latest.current.record = next;
    setRecord(next);
    latest.current.onPanelChange?.(next);
  }, []);
  const choose = useCallback(open => change({ open }), [change]);
  const frame = usePanelFrame({ has: true, mobile, frameWidth, choice: record.open, onChoice: choose, early: true });
  const { mode, peek, toggle, closePeek } = frame;
  const changeWidth = useCallback(width => change({ width }), [change]);
  const { drawnWidth, grip } = usePanelWidth({ width: clampPanelWidth(record.width), minWidth: MIN_PANEL_WIDTH, maxWidth: MAX_PANEL_WIDTH, onWidthChange: changeWidth });
  // ⌘\ (Ctrl+\): the toggle's key, from anywhere on the home but a field being typed in.
  useEffect(() => {
    const press = event => {
      if (event.defaultPrevented || event.repeat || !isPanelKey(event)) return;
      if (event.target instanceof Element && event.target.closest("input, textarea, select, [contenteditable]")) return;
      event.preventDefault();
      toggle();
    };
    document.addEventListener("keydown", press);
    return () => document.removeEventListener("keydown", press);
  }, [toggle]);
  // A place chosen in a phone's sheet is shown, so the sheet gives the page back; a peek stays until it is left.
  const closeSheet = frame.sheet.close;
  const onVisit = places?.onVisit;
  const visit = useCallback(place => { closeSheet(); onVisit?.(place); }, [closeSheet, onVisit]);
  // The panel's foot is there wherever the file viewer hands the app's menu (`PanelFoot`).
  const footed = Boolean(useAppMenu());
  const list = onPlace => (places ? <PlacesList {...places} onVisit={onPlace} footed={footed} />
    : <div className={placesClass(footed)} aria-busy="true" data-library-places=""><TreeRowsLoading label={t("home.loadingProjects")} /></div>);
  const label = t("home.sidebar");
  const foot = <PanelFoot />;
  const peeking = mode === "closed" && peek.shown;
  return <div ref={setElement} className="relative flex min-h-0 min-w-0 flex-1" data-library-frame="" data-sidebar={mobile ? undefined : mode} data-sidebar-peek={peek.peeking ? "" : undefined}
    onPointerDownCapture={event => {
      // A press on the page puts a peek away (the keyboard goes where the press does). Not one in the peek itself, nor
      // in a menu opened from it, which stands outside the frame (React hands its presses up through here all the same).
      const target = event.target;
      if (peek.peeking && target instanceof Node && event.currentTarget.contains(target) && !peek.panelRef.current?.contains(target)) closePeek(false);
    }}>
    {mobile ? <PanelSheet sheet={frame.sheet} label={label}>
      <PanelSurface mode="page" label={label} open width={drawnWidth} grip={null} gripLabel="" head={null} foot={foot} data-library-sidebar="page">
        {list(visit)}
      </PanelSurface>
    </PanelSheet> : <PanelSurface mode="push" label={label} open={mode !== "closed" || peek.shown} peek={peeking} peekLeaving={peek.leaving} peekEntered={peek.entered}
      onPeekExited={peek.exited} asideRef={peek.panelRef} {...peek.panelHandlers} width={drawnWidth} grip={grip} gripLabel={t("flatPanel.resize")}
      head={null} foot={foot} data-library-sidebar="docked">
      {list(onVisit)}
    </PanelSurface>}
    {children}
  </div>;
}
