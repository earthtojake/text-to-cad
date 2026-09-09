import { useEffect } from "react";

import { getCadWorkspaceLayoutMode } from "../../../workbench/breakpoints.js";

export const CAD_WORKSPACE_MIN_MODEL_VIEWPORT_WIDTH = 700;

function readWindowViewportWidth(fallback = 1600) {
  const width = Number(window.innerWidth);
  return Number.isFinite(width) && width > 0 ? width : fallback;
}

// The width the layout is laid out IN. The standalone viewer owns the window,
// so that is the window; an embedded surface (the desktop app's file tab) is
// one pane of a larger window, and laying its panel column out for the
// window's width leaves no viewport at all in a narrow pane. When a host
// element is given, its own width is the viewport.
function readHostViewportWidth(host, fallback = 1600) {
  const width = host ? Number(host.getBoundingClientRect().width) : 0;
  return Number.isFinite(width) && width > 0 ? width : readWindowViewportWidth(fallback);
}

// Run `sync` now, on window resizes, and — when there is a host element — on
// its resizes too; a pane resized by a drag handle sees no window event.
function watchViewport(host, sync) {
  sync();
  window.addEventListener("resize", sync);
  const observer = host && typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => sync()) : null;
  observer?.observe(host);
  return () => {
    window.removeEventListener("resize", sync);
    observer?.disconnect();
  };
}

export function preferredPanelWidthAfterViewportSync(width, minWidth = 0) {
  const numericWidth = Number(width);
  if (!Number.isFinite(numericWidth)) {
    return minWidth;
  }
  return Math.max(minWidth, numericWidth);
}

function clampPanelWidthForLayout(value, minWidth, maxWidth) {
  const numericValue = Number(value);
  const numericMinWidth = Number(minWidth);
  const numericMaxWidth = Number(maxWidth);
  const normalizedMinWidth = Number.isFinite(numericMinWidth) && numericMinWidth > 0 ? numericMinWidth : 0;
  const normalizedMaxWidth = Number.isFinite(numericMaxWidth) && numericMaxWidth > 0
    ? Math.max(normalizedMinWidth, numericMaxWidth)
    : normalizedMinWidth;
  const normalizedValue = Number.isFinite(numericValue) ? numericValue : normalizedMinWidth;
  return Math.min(Math.max(normalizedValue, normalizedMinWidth), normalizedMaxWidth);
}

export function maxPanelWidthForViewport(viewportWidth, maxWidth, { openPanelCount = 1 } = {}) {
  const numericMaxWidth = Number(maxWidth);
  const normalizedMaxWidth = Number.isFinite(numericMaxWidth) && numericMaxWidth > 0 ? numericMaxWidth : 0;
  const numericViewportWidth = Number(viewportWidth);
  if (!Number.isFinite(numericViewportWidth) || numericViewportWidth <= 0) {
    return normalizedMaxWidth;
  }

  const normalizedOpenPanelCount = Math.max(1, Math.trunc(Number(openPanelCount) || 1));
  const reservedModelWidth = Math.max(0, CAD_WORKSPACE_MIN_MODEL_VIEWPORT_WIDTH);
  const viewportPanelBudget = Math.max(0, numericViewportWidth - reservedModelWidth);
  const perPanelBudget = Math.floor(viewportPanelBudget / normalizedOpenPanelCount);
  return Math.min(
    normalizedMaxWidth,
    Math.floor(numericViewportWidth * 0.42),
    perPanelBudget
  );
}

export function canFitDesktopPanels(viewportWidth, panelMinWidths = []) {
  const numericViewportWidth = Number(viewportWidth);
  if (!Number.isFinite(numericViewportWidth) || numericViewportWidth <= 0) {
    return true;
  }
  const totalPanelMinWidth = (Array.isArray(panelMinWidths) ? panelMinWidths : [])
    .reduce((total, width) => {
      const numericWidth = Number(width);
      return total + (Number.isFinite(numericWidth) && numericWidth > 0 ? numericWidth : 0);
    }, 0);
  return numericViewportWidth >= CAD_WORKSPACE_MIN_MODEL_VIEWPORT_WIDTH + totalPanelMinWidth;
}

/**
 * The panel column's width, clamped to its own range.
 *
 * There is ONE panel column now — the surface's theme editor, its Inspector
 * and the file tree take turns in it (`cad-viewer/shell`'s `panels.js`), and
 * before that there were two, a file list on the left and this one on the
 * right. This used to solve for both at once and answer with a pair; with one
 * column the answer is one number, and the model viewport's reserve is
 * deliberately NOT enforced here: a person who drags a panel wider than the
 * reserve means it.
 */
export function resolveDesktopPanelWidth({
  open = false,
  width = 0,
  minWidth = 0,
  maxWidth = 0
} = {}) {
  return open ? clampPanelWidthForLayout(width, minWidth, Number(maxWidth)) : 0;
}

export function useCadWorkspaceLayout({
  isDesktop,
  setLayoutMode,
  setTabToolsOpen,
  setLayoutViewportWidth,
  clampTabToolsWidth,
  setTabToolsWidth,
  tabToolsResizeStateRef,
  tabToolsMinWidth,
  endTabToolsResize,
  /** The element the surface is laid out in; null means the window. */
  hostRef = null
}) {
  useEffect(() => {
    const host = hostRef?.current ?? null;
    return watchViewport(host, () => {
      setLayoutMode(getCadWorkspaceLayoutMode(readHostViewportWidth(host)));
    });
  }, [hostRef, setLayoutMode]);

  useEffect(() => {
    if (!isDesktop) {
      return undefined;
    }

    const host = hostRef?.current ?? null;
    return watchViewport(host, () => {
      setLayoutViewportWidth((current) => readHostViewportWidth(host, current));
      setTabToolsWidth((current) => preferredPanelWidthAfterViewportSync(current, tabToolsMinWidth));
    });
  }, [
    hostRef,
    isDesktop,
    setLayoutViewportWidth,
    setTabToolsWidth,
    tabToolsMinWidth
  ]);

  useEffect(() => {
    const handlePointerMove = (event) => {
      const resizeState = tabToolsResizeStateRef.current;
      if (!resizeState) {
        return;
      }

      const nextWidth = resizeState.startWidth - (event.clientX - resizeState.startX);
      if (nextWidth < tabToolsMinWidth) {
        setTabToolsWidth(tabToolsMinWidth);
        setTabToolsOpen(false);
        endTabToolsResize();
        return;
      }
      setTabToolsWidth(clampTabToolsWidth(nextWidth));
    };

    const endResize = () => {
      if (!tabToolsResizeStateRef.current) {
        return;
      }
      endTabToolsResize();
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", endResize);
    window.addEventListener("pointercancel", endResize);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", endResize);
      window.removeEventListener("pointercancel", endResize);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [
    clampTabToolsWidth,
    endTabToolsResize,
    setTabToolsOpen,
    setTabToolsWidth,
    tabToolsMinWidth,
    tabToolsResizeStateRef
  ]);
}
