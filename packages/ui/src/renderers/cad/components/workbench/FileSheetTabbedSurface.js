import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Rows2 } from "lucide-react";
import { cn } from "@hardcore/ui/utils";
import {
  activateFileSheetTab,
  clampSplitRatio,
  FILE_SHEET_TAB_PANES,
  kindSupportsSplit,
  moveFileSheetTab,
  normalizeFileSheetTabArrangement,
  resolveFileSheetTabPanes,
  setFileSheetTabRatio
} from "../../workbench/fileSheetTabLayout.js";
import { ScrollArea } from "@hardcore/ui/primitives/scroll-area";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@hardcore/ui/primitives/tabs";
import { useFileSheetTabPreferences } from "../../workbench/fileSheetTabPreferences.js";

// Per-kind tab arrangement (pane assignment, order, split, ratio), persisted
// by the host. Active tab selection stays per-file via openSectionIds.
function useFileSheetTabArrangement(kind, sectionIds) {
  const preferences = useFileSheetTabPreferences();
  const preferencesRef = useRef(preferences);
  preferencesRef.current = preferences;
  const sectionKey = sectionIds.join("|");
  const sectionIdsRef = useRef(sectionIds);
  sectionIdsRef.current = sectionIds;

  const [store, setStore] = useState(() => ({}));
  const storeRef = useRef(store);
  storeRef.current = store;

  // Hydrate from storage on the client after mount to avoid SSR mismatches.
  useEffect(() => {
    const stored = preferencesRef.current.store;
    if (stored && Object.keys(stored).length) {
      setStore(stored);
    }
  }, []);

  const arrangement = useMemo(
    () => normalizeFileSheetTabArrangement(store[kind], kind, sectionIds),
    // sectionKey captures sectionIds identity.
    [store, kind, sectionKey] // eslint-disable-line react-hooks/exhaustive-deps
  );

  const updateArrangement = useCallback((updater) => {
    const current = storeRef.current;
    const ids = sectionIdsRef.current;
    const base = normalizeFileSheetTabArrangement(current[kind], kind, ids);
    const next = typeof updater === "function" ? updater(base) : updater;
    const normalized = normalizeFileSheetTabArrangement(next, kind, ids);
    const nextStore = { ...current, [kind]: normalized };
    storeRef.current = nextStore;
    setStore(nextStore);
    preferencesRef.current.update(nextStore);
  }, [kind]);

  return [arrangement, updateArrangement];
}

function FileSheetTab({
  section,
  pane,
  dragging,
  onDragStart,
  onDragEnd
}) {
  return (
    <TabsTrigger
      value={section.id}
      title={section.titleAttr || undefined}
      data-file-sheet-tab={section.id}
      draggable
      onDragStart={(event) => {
        event.dataTransfer.effectAllowed = "move";
        try {
          event.dataTransfer.setData("text/plain", section.id);
        } catch {
          // Some browsers disallow setData outside trusted handlers; ignore.
        }
        onDragStart(section.id, pane);
      }}
      onDragEnd={onDragEnd}
      className={cn(
        "max-w-[12rem] flex-none select-none",
        dragging && "opacity-40"
      )}
    >
      <span className="min-w-0 truncate">{section.title}</span>
    </TabsTrigger>
  );
}

// Keep visited inspection trees mounted so tab switches retain disclosure and scroll state.
// Other sections retain their existing mount/unmount lifecycle.
function FileSheetTabContent({ section, active, hasTabs }) {
  const [visited, setVisited] = useState(active);
  useEffect(() => { if (active) setVisited(true); }, [active]);
  if (!active && (!section.keepMounted || !visited)) return null;
  const content = typeof section.content === "function" ? section.content(active) : section.content;
  return <TabsContent value={section.id} forceMount hidden={!active} {...(!hasTabs && { role: "region", "aria-label": section.title, "aria-labelledby": undefined })} className={cn("min-h-0 flex-1 overflow-hidden", active && "flex flex-col")} data-file-sheet-tab-panel={section.id}>
    {section.scrollsContent ? content : <ScrollArea className="min-h-0 flex-1" viewportClassName="h-full">{content}</ScrollArea>}
  </TabsContent>;
}

function FileSheetTabPane({
  pane,
  tabs,
  activeId,
  sectionsById,
  dragId,
  dropIndex,
  isDropPane,
  onActivate,
  onDragStartTab,
  onDragEndTab,
  onPaneDragOver,
  onPaneDrop,
  onPaneDragLeave
}) {
  const stripRef = useRef(null);

  return (
    <Tabs
      value={activeId}
      onValueChange={id => onActivate(pane, id)}
      className="min-h-0 min-w-0 flex-1 gap-0"
      data-file-sheet-tab-pane={pane}
      onDragOver={(event) => onPaneDragOver(event, pane, stripRef.current)}
      onDrop={(event) => onPaneDrop(event, pane)}
      onDragLeave={onPaneDragLeave}
    >
      {sectionsById.size > 1 && <TabsList
        aria-label="Model panels"
        ref={stripRef}
        className={cn(
          "mx-2 my-2 max-w-[calc(100%-1rem)] shrink-0 justify-start overflow-x-auto [scrollbar-width:none] [&::-webkit-scrollbar]:hidden",
          isDropPane && "bg-accent/20"
        )}
      >
        {tabs.map((id, index) => {
          const section = sectionsById.get(id);
          if (!section) {
            return null;
          }
          return (
            <span key={id} className="relative flex h-full items-stretch">
              {isDropPane && dropIndex === index ? (
                <span className="absolute inset-y-0 -left-px z-10 w-0.5 bg-primary" aria-hidden="true" />
              ) : null}
              <FileSheetTab
                section={section}
                pane={pane}
                dragging={id === dragId}
                onDragStart={onDragStartTab}
                onDragEnd={onDragEndTab}
              />
            </span>
          );
        })}
        {isDropPane && dropIndex >= tabs.length ? (
          <span className="relative flex h-full items-stretch">
            <span className="absolute inset-y-0 left-0 z-10 w-0.5 bg-primary" aria-hidden="true" />
          </span>
        ) : null}
      </TabsList>}
      {tabs.map(id => {
        const section = sectionsById.get(id);
        return section ? <FileSheetTabContent key={id} section={section} active={id === activeId} hasTabs={sectionsById.size > 1} /> : null;
      })}
    </Tabs>
  );
}

function computeDropIndex(stripEl, clientX) {
  if (!stripEl) {
    return null;
  }
  const tabEls = stripEl.querySelectorAll("[data-file-sheet-tab]");
  let index = 0;
  for (const tabEl of tabEls) {
    const rect = tabEl.getBoundingClientRect();
    if (clientX < rect.left + rect.width / 2) {
      return index;
    }
    index += 1;
  }
  return index;
}

export default function FileSheetTabbedSurface({
  kind,
  sections,
  openSectionIds = [],
  onOpenSectionIdsChange
}) {
  const visibleSections = useMemo(
    () => (Array.isArray(sections) ? sections.filter(Boolean) : []),
    [sections]
  );
  const sectionIds = useMemo(() => visibleSections.map((section) => section.id), [visibleSections]);
  const sectionsById = useMemo(() => {
    const map = new Map();
    for (const section of visibleSections) {
      map.set(section.id, section);
    }
    return map;
  }, [visibleSections]);

  const [arrangement, updateArrangement] = useFileSheetTabArrangement(kind, sectionIds);
  const resolved = useMemo(
    () => resolveFileSheetTabPanes(arrangement, kind, openSectionIds),
    [arrangement, kind, openSectionIds]
  );

  const [dragId, setDragId] = useState("");
  const dragIdRef = useRef("");
  const [dropTarget, setDropTarget] = useState(null);
  const [splitZoneActive, setSplitZoneActive] = useState(false);
  const [liveRatio, setLiveRatio] = useState(null);
  const containerRef = useRef(null);
  const dividerDraggingRef = useRef(false);

  const handleActivate = useCallback((pane, sectionId) => {
    onOpenSectionIdsChange?.(activateFileSheetTab(openSectionIds, arrangement, kind, pane, sectionId));
  }, [arrangement, kind, onOpenSectionIdsChange, openSectionIds]);

  const handleDragStartTab = useCallback((sectionId) => {
    dragIdRef.current = sectionId;
    setDragId(sectionId);
  }, []);

  const clearDrag = useCallback(() => {
    dragIdRef.current = "";
    setDragId("");
    setDropTarget(null);
    setSplitZoneActive(false);
  }, []);

  const handlePaneDragOver = useCallback((event, pane, stripEl) => {
    if (!dragIdRef.current) {
      return;
    }
    event.preventDefault();
    event.dataTransfer.dropEffect = "move";
    setSplitZoneActive(false);
    const index = computeDropIndex(stripEl, event.clientX);
    setDropTarget({ pane, index: index == null ? 0 : index });
  }, []);

  const handlePaneDragLeave = useCallback((event) => {
    // Only clear when leaving the pane entirely (not when moving onto a child).
    if (event.currentTarget.contains(event.relatedTarget)) {
      return;
    }
    setDropTarget((current) => (current ? null : current));
  }, []);

  const handlePaneDrop = useCallback((event, pane) => {
    const sectionId = dragIdRef.current;
    if (!sectionId) {
      return;
    }
    event.preventDefault();
    const targetIndex = dropTarget && dropTarget.pane === pane ? dropTarget.index : undefined;
    const nextArrangement = moveFileSheetTab(arrangement, kind, sectionId, pane, targetIndex);
    updateArrangement(nextArrangement);
    const landedPane = (nextArrangement.bottom || []).includes(sectionId)
      ? FILE_SHEET_TAB_PANES.BOTTOM
      : FILE_SHEET_TAB_PANES.TOP;
    onOpenSectionIdsChange?.(
      activateFileSheetTab(openSectionIds, nextArrangement, kind, landedPane, sectionId)
    );
    clearDrag();
  }, [arrangement, clearDrag, dropTarget, kind, onOpenSectionIdsChange, openSectionIds, updateArrangement]);

  // Dropping a tab into the bottom zone of a single strip splits the view.
  const canSplit = kindSupportsSplit(kind) && sectionIds.length > 1;

  const handleSplitZoneDragOver = useCallback((event) => {
    if (!dragIdRef.current) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    event.dataTransfer.dropEffect = "move";
    setDropTarget(null);
    setSplitZoneActive(true);
  }, []);

  const handleSplitZoneDragLeave = useCallback((event) => {
    if (event.currentTarget.contains(event.relatedTarget)) {
      return;
    }
    setSplitZoneActive(false);
  }, []);

  const handleSplitDrop = useCallback((event) => {
    const sectionId = dragIdRef.current;
    if (!sectionId) {
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const nextArrangement = moveFileSheetTab(arrangement, kind, sectionId, FILE_SHEET_TAB_PANES.BOTTOM, 0);
    updateArrangement(nextArrangement);
    onOpenSectionIdsChange?.(
      activateFileSheetTab(openSectionIds, nextArrangement, kind, FILE_SHEET_TAB_PANES.BOTTOM, sectionId)
    );
    clearDrag();
  }, [arrangement, clearDrag, kind, onOpenSectionIdsChange, openSectionIds, updateArrangement]);

  // Divider resize.
  const handleDividerPointerDown = useCallback((event) => {
    event.preventDefault();
    dividerDraggingRef.current = true;
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }, []);

  const handleDividerPointerMove = useCallback((event) => {
    if (!dividerDraggingRef.current || !containerRef.current) {
      return;
    }
    const rect = containerRef.current.getBoundingClientRect();
    if (rect.height <= 0) {
      return;
    }
    setLiveRatio(clampSplitRatio((event.clientY - rect.top) / rect.height));
  }, []);

  const handleDividerPointerUp = useCallback((event) => {
    if (!dividerDraggingRef.current) {
      return;
    }
    dividerDraggingRef.current = false;
    event.currentTarget.releasePointerCapture?.(event.pointerId);
    setLiveRatio((ratio) => {
      if (ratio != null) {
        updateArrangement((current) => setFileSheetTabRatio(current, ratio));
      }
      return null;
    });
  }, [updateArrangement]);

  const renderPane = (paneInfo) => (
    <FileSheetTabPane
      pane={paneInfo.pane}
      tabs={paneInfo.tabs}
      activeId={paneInfo.activeId}
      sectionsById={sectionsById}
      dragId={dragId}
      dropIndex={dropTarget && dropTarget.pane === paneInfo.pane ? dropTarget.index : -1}
      isDropPane={Boolean(dragId) && dropTarget?.pane === paneInfo.pane}
      onActivate={handleActivate}
      onDragStartTab={handleDragStartTab}
      onDragEndTab={clearDrag}
      onPaneDragOver={handlePaneDragOver}
      onPaneDrop={handlePaneDrop}
      onPaneDragLeave={handlePaneDragLeave}
    />
  );

  if (!resolved.split) {
    return (
      <div className="relative flex min-h-0 flex-1 flex-col">
        {renderPane(resolved.panes[0])}
        {canSplit && dragId ? (
          <div
            data-file-sheet-split-zone=""
            onDragOver={handleSplitZoneDragOver}
            onDragLeave={handleSplitZoneDragLeave}
            onDrop={handleSplitDrop}
            className={cn(
              "absolute inset-x-0 bottom-0 z-20 flex h-1/2 items-center justify-center border-t-2 border-dashed transition-colors",
              splitZoneActive
                ? "border-primary bg-primary/15"
                : "border-sidebar-border/70 bg-background/30"
            )}
          >
            <span className="pointer-events-none flex items-center gap-1.5 text-tiny text-muted-foreground">
              <Rows2 className="size-3.5" strokeWidth={2} aria-hidden="true" />
              Drop here to split
            </span>
          </div>
        ) : null}
      </div>
    );
  }

  const ratio = liveRatio == null ? resolved.ratio : liveRatio;
  const [topPane, bottomPane] = resolved.panes;

  return (
    <div ref={containerRef} className="flex min-h-0 flex-1 flex-col">
      <div
        className="flex min-h-0 min-w-0 flex-col"
        style={{ flex: `0 0 ${ratio * 100}%` }}
      >
        {renderPane(topPane)}
      </div>
      <div
        role="separator"
        aria-orientation="horizontal"
        aria-label="Resize tab panes"
        onPointerDown={handleDividerPointerDown}
        onPointerMove={handleDividerPointerMove}
        onPointerUp={handleDividerPointerUp}
        className="relative z-10 h-px shrink-0 cursor-row-resize touch-none bg-sidebar-border transition-colors before:absolute before:inset-x-0 before:-top-[3px] before:h-[7px] before:content-[''] hover:bg-ring"
      />
      <div className="flex min-h-0 min-w-0 flex-1 flex-col">
        {renderPane(bottomPane)}
      </div>
    </div>
  );
}
