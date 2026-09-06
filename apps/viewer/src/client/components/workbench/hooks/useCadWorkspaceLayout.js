import { useEffect } from "react";

import { getCadWorkspaceLayoutMode } from "../../../workbench/breakpoints.js";

const SIDEBAR_WRAPPER_SELECTOR = "[data-slot='sidebar-wrapper']";
export const CAD_WORKSPACE_MIN_MODEL_VIEWPORT_WIDTH = 700;

function sidebarWrapperElement() {
  return document.querySelector(SIDEBAR_WRAPPER_SELECTOR);
}

function applySidebarWidth(width) {
  sidebarWrapperElement()?.style.setProperty("--sidebar-width", `${width}px`);
}

function readWindowViewportWidth(fallback = 1600) {
  const width = Number(window.innerWidth);
  return Number.isFinite(width) && width > 0 ? width : fallback;
}

// The width the layout is laid out IN. The standalone viewer owns the window,
// so that is the window; an embedded surface (the desktop app's file tab) is
// one pane of a larger window, and laying its sidebar and sheet out for the
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

export function resolveDesktopPanelWidths({
  viewportWidth,
  sidebarOpen = false,
  sheetOpen = false,
  sidebarWidth = 0,
  sheetWidth = 0,
  sidebarMinWidth = 0,
  sheetMinWidth = 0,
  sidebarMaxWidth = 0,
  sheetMaxWidth = 0
} = {}) {
  if (!sidebarOpen && !sheetOpen) {
    return { sidebarWidth: 0, sheetWidth: 0 };
  }

  const sidebarMax = Number(sidebarMaxWidth);
  const sheetMax = Number(sheetMaxWidth);

  if (sidebarOpen && !sheetOpen) {
    return {
      sidebarWidth: clampPanelWidthForLayout(sidebarWidth, sidebarMinWidth, sidebarMax),
      sheetWidth: 0
    };
  }

  if (!sidebarOpen && sheetOpen) {
    return {
      sidebarWidth: 0,
      sheetWidth: clampPanelWidthForLayout(sheetWidth, sheetMinWidth, sheetMax)
    };
  }

  const sidebarMin = Math.max(0, Number(sidebarMinWidth) || 0);
  const sheetMin = Math.max(0, Number(sheetMinWidth) || 0);
  let nextSidebarWidth = clampPanelWidthForLayout(sidebarWidth, sidebarMin, sidebarMax);
  let nextSheetWidth = clampPanelWidthForLayout(sheetWidth, sheetMin, sheetMax);

  return {
    sidebarWidth: nextSidebarWidth,
    sheetWidth: nextSheetWidth
  };
}

export function useCadWorkspaceLayout({
  isDesktop,
  setLayoutMode,
  setSidebarOpen,
  setTabToolsOpen,
  setLayoutViewportWidth,
  clampSidebarWidth,
  clampTabToolsWidth,
  setSidebarWidth,
  setTabToolsWidth,
  panelResizeStateRef,
  tabToolsResizeStateRef,
  defaultSidebarWidth,
  sidebarMinWidth,
  tabToolsMinWidth,
  endPanelResize,
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
      setSidebarWidth((current) => preferredPanelWidthAfterViewportSync(current, sidebarMinWidth));
      setTabToolsWidth((current) => preferredPanelWidthAfterViewportSync(current, tabToolsMinWidth));
    });
  }, [
    hostRef,
    isDesktop,
    setLayoutViewportWidth,
    setSidebarWidth,
    setTabToolsWidth,
    sidebarMinWidth,
    tabToolsMinWidth
  ]);

  useEffect(() => {
    const handlePointerMove = (event) => {
      const resizeState = panelResizeStateRef.current;
      if (!resizeState) {
        return;
      }

      const rawWidth = resizeState.startWidth + (event.clientX - resizeState.startX);
      if (rawWidth < sidebarMinWidth) {
        applySidebarWidth(defaultSidebarWidth);
        setSidebarWidth(defaultSidebarWidth);
        setSidebarOpen(false);
        endPanelResize();
        return;
      }

      const nextWidth = clampSidebarWidth(rawWidth);
      resizeState.latestWidth = nextWidth;
      applySidebarWidth(nextWidth);
      setSidebarWidth(nextWidth);
    };

    const endResize = () => {
      const resizeState = panelResizeStateRef.current;
      if (!resizeState) {
        return;
      }
      const nextWidth = Math.max(
        sidebarMinWidth,
        clampSidebarWidth(resizeState.latestWidth ?? resizeState.startWidth)
      );
      applySidebarWidth(nextWidth);
      setSidebarWidth(nextWidth);
      endPanelResize();
    };

    window.addEventListener("pointermove", handlePointerMove);
    window.addEventListener("pointerup", endResize);
    window.addEventListener("pointercancel", endResize);
    return () => {
      window.removeEventListener("pointermove", handlePointerMove);
      window.removeEventListener("pointerup", endResize);
      window.removeEventListener("pointercancel", endResize);
      if (!tabToolsResizeStateRef.current) {
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }
    };
  }, [
    clampSidebarWidth,
    endPanelResize,
    panelResizeStateRef,
    defaultSidebarWidth,
    setSidebarOpen,
    setSidebarWidth,
    sidebarMinWidth,
    tabToolsResizeStateRef
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
      if (!panelResizeStateRef.current) {
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
      }
    };
  }, [
    clampTabToolsWidth,
    endTabToolsResize,
    panelResizeStateRef,
    setTabToolsOpen,
    setTabToolsWidth,
    tabToolsMinWidth,
    tabToolsResizeStateRef
  ]);
}
