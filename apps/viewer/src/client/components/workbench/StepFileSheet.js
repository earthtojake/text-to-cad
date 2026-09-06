import { useEffect, useMemo, useRef } from "react";
import { Box, Boxes, ChevronRight, Eye, EyeOff, X } from "lucide-react";
import { cn } from "@/ui/utils";
import {
  STEP_MODEL_ROOT_ID,
  flattenVisibleStepTreeRows,
  stepTreeNodeChildren
} from "cadgen-js/lib/step/stepTree";
import { Button } from "../ui/button";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuSeparator,
  ContextMenuTrigger
} from "../ui/context-menu";
import FileSheet, {
  FileSheetStatusText
} from "./FileSheet";
import FileSheetTabbedSurface from "./FileSheetTabbedSurface";
import AssemblyContextMenuItems from "./AssemblyContextMenuItems";
import { buildFileStatusTab } from "./FileStatusSection";
import { buildPoseControlsTab } from "./PoseControlsSection";
import { buildAnimationControlsTab } from "./AnimationControlsSection";
import { buildStepReferenceTab } from "./StepReferenceSection";
import StepMeasurementsSection from "./StepMeasurementsSection";
import { FILE_SHEET_SECTION_IDS } from "../../workbench/fileSheetSections";
const treeChevronButtonClasses = "grid h-5 w-5 shrink-0 place-items-center rounded-sm px-0 text-current/60 hover:bg-sidebar-accent/45 hover:text-sidebar-accent-foreground focus-visible:bg-sidebar-accent/45";
const treeRowActionButtonClasses = "h-5 w-5 rounded-sm px-0 text-current/60 shadow-none hover:bg-sidebar-accent/45 hover:text-sidebar-accent-foreground focus-visible:bg-sidebar-accent/45 focus-visible:text-sidebar-accent-foreground";
const treeRowContentClasses = "h-7 min-w-0 text-xs";
const treeGroupLabelClasses = "px-2 pb-1 pt-2 text-micro text-sidebar-foreground/45";
const treeGlyphIconClasses = "size-3.5 shrink-0 text-current/60";
// One indent level equals the expand-chevron's footprint (w-5 button + gap-1.5),
// so a leaf row's glyph (which has no chevron) lines up exactly under its
// expandable parent's glyph instead of sitting a few pixels to the left.
const treeDepthIndentPx = 26;
const treeDepthGuideOffsetPx = 14;
const treeDepthMaxPx = 156;
const treeSectionId = "tree";
const measurementsSectionId = FILE_SHEET_SECTION_IDS.STEP_MEASUREMENTS;
const EMPTY_MEASUREMENTS = [];
const treeRevealScrollPaddingTopPx = 120;

function leafIdsHidden(leafPartIds, hiddenPartIds) {
  const leafIds = Array.isArray(leafPartIds)
    ? leafPartIds.map((id) => String(id || "").trim()).filter(Boolean)
    : [];
  if (!leafIds.length) {
    return false;
  }
  const hidden = new Set(Array.isArray(hiddenPartIds) ? hiddenPartIds : []);
  return leafIds.every((id) => hidden.has(id));
}

function hiddenStepTreeRowIds(visibleRows, hiddenPartIds) {
  const hiddenRows = new Set();
  const hiddenByDepth = [];
  for (const row of Array.isArray(visibleRows) ? visibleRows : []) {
    const depth = Math.max(Number(row?.depth) || 0, 0);
    hiddenByDepth.length = depth;
    const parentHidden = depth > 0 && hiddenByDepth[depth - 1] === true;
    const rowHidden = parentHidden || leafIdsHidden(row?.leafPartIds, hiddenPartIds);
    hiddenByDepth[depth] = rowHidden;
    if (rowHidden) {
      hiddenRows.add(String(row?.id || "").trim());
    }
  }
  return hiddenRows;
}

function stepTreeNodeId(node) {
  return String(node?.id || node?.occurrenceId || "").trim();
}

function isolatedStepTreeRowIds(visibleRows, focusedNodeIds) {
  const focused = new Set(
    (Array.isArray(focusedNodeIds) ? focusedNodeIds : [])
      .map((id) => String(id || "").trim())
      .filter(Boolean)
  );
  if (!focused.size) {
    return null;
  }
  const isolatedRows = new Set();
  const isolatedByDepth = [];
  for (const row of Array.isArray(visibleRows) ? visibleRows : []) {
    const rowId = String(row?.id || "").trim();
    const depth = Math.max(Number(row?.depth) || 0, 0);
    isolatedByDepth.length = depth;
    const parentIsolated = depth > 0 && isolatedByDepth[depth - 1] === true;
    const rowIsolated = parentIsolated || focused.has(rowId);
    isolatedByDepth[depth] = rowIsolated;
    if (rowIsolated && rowId) {
      isolatedRows.add(rowId);
    }
  }
  return isolatedRows;
}

function scrollTreeNodeIntoView(target, { block = "nearest" } = {}) {
  if (!target) {
    return;
  }

  const viewport = target.closest("[data-slot='scroll-area-viewport']");
  if (!viewport) {
    target.scrollIntoView?.({
      block,
      behavior: "instant"
    });
    return;
  }

  const targetRect = target.getBoundingClientRect();
  const viewportRect = viewport.getBoundingClientRect();

  if (block === "center") {
    const targetCenter = targetRect.top + targetRect.height / 2;
    const viewportCenter = viewportRect.top + viewportRect.height / 2;
    viewport.scrollTop += targetCenter - viewportCenter;
    return;
  }

  const paddedTop = viewportRect.top + treeRevealScrollPaddingTopPx;

  if (targetRect.top < paddedTop) {
    viewport.scrollTop += targetRect.top - paddedTop;
    return;
  }

  if (targetRect.bottom > viewportRect.bottom) {
    viewport.scrollTop += targetRect.bottom - viewportRect.bottom;
  }
}

function topologyTreeRowType(row) {
  const explicitType = String(row?.topologyType || "").trim();
  if (explicitType) {
    return explicitType;
  }
  const nodeType = String(row?.nodeType || row?.node?.nodeType || "").trim();
  return nodeType.startsWith("topology-") ? nodeType.slice("topology-".length) : "";
}

function topologyTreeRowDetailText(row) {
  return String(row?.detail || row?.node?.detail || row?.summary || row?.node?.summary || "").trim();
}

function topologyTreeRowKind(row, type) {
  const detail = topologyTreeRowDetailText(row).toLowerCase();
  const label = String(row?.label || row?.node?.displayName || "").trim().toLowerCase();
  const haystack = `${detail} ${label}`;
  if (type === "face") {
    if (/\bplane\b/.test(haystack)) return "plane";
    if (/\bcylinder\b/.test(haystack)) return "cylinder";
    if (/\bcone\b/.test(haystack)) return "cone";
    if (/\bsphere\b/.test(haystack)) return "sphere";
    if (/\btorus\b/.test(haystack)) return "torus";
    if (/\bbspline\b|\bspline\b|\bbezier\b/.test(haystack)) return "spline";
    return "face";
  }
  if (type === "edge") {
    if (/\bcircle\b/.test(haystack)) return "circle";
    if (/\bellipse\b/.test(haystack)) return "ellipse";
    if (/\bline\b/.test(haystack)) return "line";
    if (/\bbspline\b|\bspline\b|\bbezier\b/.test(haystack)) return "spline";
    return "edge";
  }
  if (type === "shape") {
    if (/\bsolid\b/.test(haystack)) return "solid";
    if (/\bshell\b/.test(haystack)) return "shell";
  }
  return type;
}

function capitalizeTreeLabel(value) {
  const text = String(value || "").trim();
  return text ? `${text.slice(0, 1).toUpperCase()}${text.slice(1)}` : "";
}

function stepTreeRowAriaLabel(row, topologyType, detail = "") {
  const label = String(row?.label || row?.node?.displayName || "").trim();
  const normalizedTopologyType = String(topologyType || "").trim();
  const normalizedDetail = String(detail || "").trim();
  if (normalizedTopologyType) {
    const prefix = capitalizeTreeLabel(normalizedTopologyType);
    const normalizedLabel = label.toLowerCase();
    const shouldPrefix = prefix && !normalizedLabel.startsWith(normalizedTopologyType.toLowerCase());
    return [shouldPrefix ? prefix : "", label, normalizedDetail].filter(Boolean).join(" ");
  }
  const nodeType = String(row?.nodeType || row?.node?.nodeType || "").trim();
  const prefix = nodeType === "assembly" ? "Assembly" : "Component";
  return [prefix, label, normalizedDetail].filter(Boolean).join(" ");
}

function formatTreeTooltipLine(label, value) {
  const normalizedValue = String(value || "").trim();
  return normalizedValue ? `${label}: ${normalizedValue}` : "";
}

function formatRefForTooltip(value) {
  const normalizedValue = String(value || "").trim().replace(/^#/, "");
  return normalizedValue ? `#${normalizedValue}` : "";
}

function stepTreeRowTooltip(row, {
  topologyType = "",
  topologyReferenceId = "",
  detail = "",
  disabledReason = "",
} = {}) {
  const label = String(row?.label || row?.node?.displayName || "").trim();
  const nodeType = String(row?.nodeType || row?.node?.nodeType || "").trim();
  const type = topologyType
    ? capitalizeTreeLabel(topologyType)
    : nodeType === "assembly" ? "Assembly" : "Component";
  const selector = topologyType
    ? String(row?.node?.displaySelector || row?.displaySelector || topologyReferenceId || "").trim()
    : String(row?.node?.occurrenceId || row?.node?.id || row?.id || "").trim();
  return [
    formatTreeTooltipLine(type || "Item", label),
    formatTreeTooltipLine("Ref", formatRefForTooltip(selector)),
    formatTreeTooltipLine("Info", detail),
    formatTreeTooltipLine("Status", disabledReason),
  ].filter(Boolean).join("\n");
}

function StepTreeDepthGuides({ depth }) {
  const normalizedDepth = Math.min(
    Math.max(Math.trunc(Number(depth) || 0), 0),
    Math.floor(treeDepthMaxPx / treeDepthIndentPx)
  );

  if (normalizedDepth < 1) {
    return null;
  }

  return (
    <span className="pointer-events-none absolute inset-y-0 left-0" aria-hidden="true">
      {Array.from({ length: normalizedDepth }).map((_, index) => (
        <span
          key={index}
          className="absolute inset-y-0 border-l border-sidebar-border/65"
          style={{ left: `${index * treeDepthIndentPx + treeDepthGuideOffsetPx}px` }}
        />
      ))}
    </span>
  );
}

function TopologySvg({ children }) {
  return (
    <svg
      className={treeGlyphIconClasses}
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.45"
      strokeLinecap="round"
      strokeLinejoin="round"
      shapeRendering="geometricPrecision"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

function TopologyTreeGlyph({ row, type }) {
  const normalizedType = String(type || "").trim();
  const kind = topologyTreeRowKind(row, normalizedType);
  const common = `relative ${treeGlyphIconClasses}`;
  if (normalizedType === "occurrence") {
    return null;
  }
  if (normalizedType === "shape") {
    if (kind === "shell") {
      return (
        <TopologySvg>
          <path d="M4.5 4.5h7v7h-7z" />
          <path d="M6.25 6.25h3.5v3.5h-3.5z" />
        </TopologySvg>
      );
    }
    return (
      <span className={common} aria-hidden="true">
        <span className="absolute left-[3px] top-[3px] size-2.5 rotate-45 rounded-[1px] border border-current" />
      </span>
    );
  }
  if (normalizedType === "face") {
    if (kind === "cylinder") {
      return (
        <TopologySvg>
          <ellipse cx="8" cy="4" rx="4" ry="2" />
          <path d="M4 4v8" />
          <path d="M12 4v8" />
          <ellipse cx="8" cy="12" rx="4" ry="2" />
        </TopologySvg>
      );
    }
    if (kind === "cone") {
      return (
        <TopologySvg>
          <path d="M8 3 4 12" />
          <path d="M8 3l4 9" />
          <path d="M4 12c1.25 1.25 6.75 1.25 8 0" />
        </TopologySvg>
      );
    }
    if (kind === "sphere") {
      return (
        <TopologySvg>
          <circle cx="8" cy="8" r="5" />
          <path d="M8 3c1.3 1.35 2 3.05 2 5s-.7 3.65-2 5" />
          <path d="M3 8h10" />
        </TopologySvg>
      );
    }
    if (kind === "torus") {
      return (
        <TopologySvg>
          <ellipse cx="8" cy="8" rx="5.2" ry="3.4" />
          <ellipse cx="8" cy="8" rx="2.2" ry="1.25" />
        </TopologySvg>
      );
    }
    if (kind === "spline") {
      return (
        <TopologySvg>
          <path d="M3 11.5c2.1-6.6 7.6 1 10-5.8" />
          <path d="M3.5 12.7h8.8" opacity="0.45" />
        </TopologySvg>
      );
    }
    return (
      <span className={common} aria-hidden="true">
        <span className="absolute inset-[3px] rounded-[1px] border border-current bg-current/15" />
      </span>
    );
  }
  if (normalizedType === "edge") {
    if (kind === "circle") {
      return (
        <TopologySvg>
          <circle cx="8" cy="8" r="4.6" />
          <circle cx="8" cy="8" r="1.2" fill="currentColor" stroke="none" opacity="0.25" />
        </TopologySvg>
      );
    }
    if (kind === "ellipse") {
      return (
        <TopologySvg>
          <ellipse cx="8" cy="8" rx="5.4" ry="3.2" />
        </TopologySvg>
      );
    }
    if (kind === "spline") {
      return (
        <TopologySvg>
          <path d="M2.8 10.6c2.1-5.8 5.2 2.8 10.4-4.8" />
          <circle cx="2.8" cy="10.6" r="0.9" fill="currentColor" stroke="none" />
          <circle cx="13.2" cy="5.8" r="0.9" fill="currentColor" stroke="none" />
        </TopologySvg>
      );
    }
    return (
      <span className={common} aria-hidden="true">
        <span className="absolute left-[2px] top-[7px] h-px w-3 rotate-[-28deg] rounded-full bg-current" />
        <span className="absolute left-[1px] top-[8px] size-1 rounded-full bg-current" />
        <span className="absolute right-[1px] top-[3px] size-1 rounded-full bg-current" />
      </span>
    );
  }
  return null;
}

function StepTreeRowGlyph({ row }) {
  const topologyType = topologyTreeRowType(row);
  // Topology leaves (faces/edges/shapes) keep their geometric glyph; everything
  // else — assemblies, components, and part occurrences — gets a box icon so
  // every tree row carries an icon, not only the leaf topology nodes.
  if (topologyType && topologyType !== "occurrence") {
    return <TopologyTreeGlyph row={row} type={topologyType} />;
  }
  const nodeType = String(row?.nodeType || row?.node?.nodeType || "").trim();
  const Icon = nodeType === "assembly" ? Boxes : Box;
  return <Icon className={treeGlyphIconClasses} strokeWidth={1.6} aria-hidden="true" />;
}

export default function StepFileSheet({
  open,
  measurements = EMPTY_MEASUREMENTS,
  activeMeasurementId = "",
  measureModeActive = false,
  onMeasurementActivate,
  onMeasurementDelete,
  onMeasurementsClear,
  isDesktop,
  width,
  onOpenChange,
  onStartResize,
  selectedEntry,
  viewerLoading,
  isAssemblyView = false,
  stepTreeRoot,
  expandedTreeNodeIds,
  loadableTreeNodeIds = [],
  selectedPartIds,
  selectedReferenceIds = [],
  selectedReferences = [],
  selectableNodeIds = null,
  activeTreeNodeId: activeTreeNodeIdProp = "",
  activeTreeNodeScrollKey = "",
  hoveredPartId,
  hoveredReferenceId = "",
  hiddenPartIds,
  focusedNodeIds = [],
  onSelectTreeNode,
  onSelectReferenceNode,
  onCopyTreeNodeReference,
  onFocusTreeNode,
  onUnfocusTreeNode,
  onExitAllIsolate,
  onHideOtherTreeNode,
  onToggleTreeNode,
  onClearSelection,
  onHoverTreeNode,
  onHoverReferenceNode,
  treeSelectionDisabled = false,
  treeSelectionDisabledReason = "",
  onTogglePartVisibility,
  hideAllParts,
  showAllHiddenParts,
  stepModule = null,
  stepAnimation = null,
  viewerServerInfo = null,
  suppressDynamicMetadataStatus = false,
  statusItems = [],
  themeTabs = [],
  openSectionIds = [],
  onOpenSectionIdsChange
}) {
  const rowRefs = useRef(new Map());
  const lastActiveTreeNodeScrollKeyRef = useRef("");
  const selectedIds = Array.isArray(selectedPartIds) ? selectedPartIds : [];
  const selectedReferenceIdSet = useMemo(
    () => new Set((Array.isArray(selectedReferenceIds) ? selectedReferenceIds : []).map((id) => String(id || "").trim()).filter(Boolean)),
    [selectedReferenceIds]
  );
  const activeSelectedReferenceId = String(
    Array.isArray(selectedReferenceIds) ? selectedReferenceIds[selectedReferenceIds.length - 1] || "" : ""
  ).trim();
  const hiddenIds = Array.isArray(hiddenPartIds) ? hiddenPartIds : [];
  const focusedNodeIdSet = useMemo(
    () => new Set((Array.isArray(focusedNodeIds) ? focusedNodeIds : []).map((id) => String(id || "").trim()).filter(Boolean)),
    [focusedNodeIds]
  );
  const normalizedHoveredReferenceId = String(hoveredReferenceId || "").trim();
  const selectableNodeIdSet = useMemo(() => {
    if (!Array.isArray(selectableNodeIds)) {
      return null;
    }
    return new Set(selectableNodeIds.map((id) => String(id || "").trim()).filter(Boolean));
  }, [selectableNodeIds]);
  const treeRoot = stepTreeRoot;
  const treeRootChildren = stepTreeNodeChildren(treeRoot);
  const elideRootTreeRow = treeRootChildren.length > 0 && (
    isAssemblyView ||
    stepTreeNodeId(treeRoot) === STEP_MODEL_ROOT_ID
  );
  const visibleRows = useMemo(
    () => flattenVisibleStepTreeRows(treeRoot, expandedTreeNodeIds, {
      omitRoot: elideRootTreeRow,
      showAllRootChildren: true
    }),
    [elideRootTreeRow, expandedTreeNodeIds, treeRoot]
  );
  const visibleRowIdsSignature = useMemo(
    () => visibleRows.map((row) => String(row?.id || "")).join("\n"),
    [visibleRows]
  );
  const hiddenTreeRowIds = useMemo(
    () => hiddenStepTreeRowIds(visibleRows, hiddenIds),
    [hiddenIds, visibleRows]
  );
  const isolatedTreeRowIds = useMemo(
    () => isolatedStepTreeRowIds(visibleRows, focusedNodeIds),
    [focusedNodeIds, visibleRows]
  );
  const hasAssemblyTree = isAssemblyView || elideRootTreeRow
    ? visibleRows.length > 0
    : visibleRows.some((row) => row?.hasChildren);
  // The tree header counts what the file holds at its TOP level, the number a user reads as
  // "how many parts is this". Not the flattened row count, which includes every expanded
  // child and would change under them as they open nodes.
  const topLevelPartCount = useMemo(
    () => visibleRows.filter((row) => Number(row?.depth || 0) === 0).length,
    [visibleRows]
  );
  // Show All renders only when something is hidden, so a fully visible tree keeps a header
  // with nothing to click.
  const hasHiddenTreeRows = hiddenTreeRowIds.size > 0;
  const activeReferenceTreeRow = useMemo(
    () => activeSelectedReferenceId
      ? visibleRows.find((row) => String(row?.topologyReferenceId || "").trim() === activeSelectedReferenceId) || null
      : null,
    [activeSelectedReferenceId, visibleRows]
  );
  const rawActiveTreeNodeId = String(activeTreeNodeIdProp || selectedIds[selectedIds.length - 1] || "").trim();
  const activeTreeNodeId = String(activeReferenceTreeRow?.id || rawActiveTreeNodeId || "").trim();
  const activeTreeRow = useMemo(
    () => activeTreeNodeId
      ? visibleRows.find((row) => (
          String(row?.id || "").trim() === activeTreeNodeId ||
          String(row?.node?.selectionPartId || "").trim() === activeTreeNodeId
        )) || null
      : null,
    [activeTreeNodeId, visibleRows]
  );
  const activeTreeNodeIsTopology = activeTreeRow?.node?.visualOnly === true
    ? false
    : Boolean(topologyTreeRowType(activeTreeRow));
  const isolateActive = focusedNodeIdSet.size > 0;
  const showTreeVisibilityControls = isAssemblyView === true;
  const treeSectionOpen = Array.isArray(openSectionIds) && openSectionIds.includes(treeSectionId);
  const treeSelectionTitle = treeSelectionDisabled
    ? String(treeSelectionDisabledReason || "Tree selection is disabled in the current parameter state.").trim()
    : "";
  const expandedTreeNodeIdSet = useMemo(
    () => new Set((Array.isArray(expandedTreeNodeIds) ? expandedTreeNodeIds : []).map((id) => String(id || "").trim()).filter(Boolean)),
    [expandedTreeNodeIds]
  );
  const loadableTreeNodeIdSet = useMemo(
    () => new Set((Array.isArray(loadableTreeNodeIds) ? loadableTreeNodeIds : []).map((id) => String(id || "").trim()).filter(Boolean)),
    [loadableTreeNodeIds]
  );
  const rowCanExpandOrLoad = (row) => {
    const rowId = String(row?.id || "").trim();
    return Boolean(row?.hasChildren || (rowId && loadableTreeNodeIdSet.has(rowId)));
  };
  const expandableTreeNodeIds = useMemo(() => {
    const ids = [];
    const seen = new Set();
    for (const row of visibleRows) {
      const rowId = String(row?.id || "").trim();
      if (!rowId || seen.has(rowId)) {
        continue;
      }
      if (rowCanExpandOrLoad(row)) {
        seen.add(rowId);
        ids.push(rowId);
      }
    }
    return ids;
  }, [loadableTreeNodeIdSet, visibleRows]);
  const collapsedExpandableTreeNodeIds = useMemo(
    () => expandableTreeNodeIds.filter((nodeId) => !expandedTreeNodeIdSet.has(nodeId)),
    [expandableTreeNodeIds, expandedTreeNodeIdSet]
  );
  const expandedExpandableTreeNodeIds = useMemo(
    () => expandableTreeNodeIds.filter((nodeId) => expandedTreeNodeIdSet.has(nodeId)),
    [expandableTreeNodeIds, expandedTreeNodeIdSet]
  );
  const visibleRowById = useMemo(() => {
    const map = new Map();
    for (const row of visibleRows) {
      const rowId = String(row?.id || "").trim();
      if (rowId) {
        map.set(rowId, row);
      }
      const selectionRowId = String(row?.node?.selectionPartId || "").trim();
      if (selectionRowId && !map.has(selectionRowId)) {
        map.set(selectionRowId, row);
      }
    }
    return map;
  }, [visibleRows]);

  const focusTreeRowAtIndex = (startIndex, direction = 1) => {
    if (!visibleRows.length) {
      return;
    }
    const step = direction < 0 ? -1 : 1;
    let index = Math.min(Math.max(Number(startIndex) || 0, 0), visibleRows.length - 1);
    while (index >= 0 && index < visibleRows.length) {
      const rowId = String(visibleRows[index]?.id || "").trim();
      const node = rowId ? rowRefs.current.get(rowId) : null;
      if (node && node.getAttribute("aria-disabled") !== "true") {
        node.focus?.();
        scrollTreeNodeIntoView(node, { block: "nearest" });
        return;
      }
      index += step;
    }
  };

  useEffect(() => {
    const scrollKey = String(activeTreeNodeScrollKey || "").trim();
    if (!scrollKey || scrollKey === lastActiveTreeNodeScrollKeyRef.current || !activeTreeNodeId || !treeSectionOpen) {
      return;
    }
    const scrollToActiveTreeNode = () => {
      const activeNode = rowRefs.current.get(activeTreeNodeId);
      if (!activeNode) {
        return;
      }
      lastActiveTreeNodeScrollKeyRef.current = scrollKey;
      scrollTreeNodeIntoView(activeNode, {
        block: activeTreeNodeIsTopology ? "center" : "nearest"
      });
    };
    if (typeof window === "undefined") {
      scrollToActiveTreeNode();
      return;
    }
    const frameId = window.requestAnimationFrame(scrollToActiveTreeNode);
    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [activeTreeNodeId, activeTreeNodeIsTopology, activeTreeNodeScrollKey, treeSectionOpen, visibleRowIdsSignature]);

  if (!selectedEntry) {
    return null;
  }

  const measurementsSection = {
    id: measurementsSectionId,
    title: "Measure",
    content: (
      <StepMeasurementsSection
        measurements={measurements}
        activeId={activeMeasurementId}
        measureModeActive={measureModeActive}
        onActivate={onMeasurementActivate}
        onDelete={onMeasurementDelete}
        onClear={onMeasurementsClear}
      />
    )
  };

  const sections = [
    {
      id: treeSectionId,
      title: "Tree",
      titleAttr: treeSelectionTitle || undefined,
      content: (
            <div className="max-w-full overflow-hidden pb-2">
              <div
                className="select-none space-y-px"
                role="tree"
                aria-multiselectable="true"
                aria-disabled={treeSelectionDisabled}
                title={treeSelectionTitle || undefined}
                onClick={(event) => {
                  if (treeSelectionDisabled) {
                    return;
                  }
                  if (event.target === event.currentTarget) {
                    onClearSelection?.();
                  }
                }}
              >
              {hasAssemblyTree ? (
                <div className="flex items-center justify-between gap-2 pr-1">
                  <div className={treeGroupLabelClasses} role="presentation">
                    Assembly
                    <span className="ml-1.5 tabular-nums text-sidebar-foreground/35">
                      {topLevelPartCount}
                    </span>
                  </div>
                  {hasHiddenTreeRows ? (
                    <button
                      type="button"
                      className="rounded-sm px-1.5 py-0.5 text-micro text-sidebar-foreground/50 transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                      onClick={() => showAllHiddenParts?.()}
                    >
                      Show All
                    </button>
                  ) : null}
                </div>
              ) : null}

              {viewerLoading && !visibleRows.length ? (
                <FileSheetStatusText className="py-1">
                  Loading STEP tree...
                </FileSheetStatusText>
              ) : null}

              {hasAssemblyTree
                ? visibleRows.map((row, rowIndex) => {
                  const visualOnlyRow = row?.node?.visualOnly === true;
                  const topologyType = visualOnlyRow ? "" : topologyTreeRowType(row);
                  const topologyRow = Boolean(topologyType);
                  const rowId = String(row.id || "").trim();
                  const selectionRowId = String(row.node?.selectionPartId || row.id || "").trim();
                  const topologyReferenceId = String(row.topologyReferenceId || "").trim();
                  const topologyPartId = topologyRow ? String(row.node?.partId || "").trim() : "";
                  const selectableTopologyRow = Boolean(topologyType) &&
                    topologyReferenceId &&
                    typeof onSelectReferenceNode === "function";
                  const rowDetail = String(row.detail || "").trim();
                  const inlineRowDetail = topologyType ? "" : rowDetail;
                  const rowAriaLabel = stepTreeRowAriaLabel(row, topologyType, rowDetail);
                  const rowHasChildren = rowCanExpandOrLoad(row);
                  const rowExpanded = Boolean(row.expanded);
                  const selected = topologyRow
                    ? selectedReferenceIdSet.has(topologyReferenceId)
                    : selectedIds.includes(selectionRowId);
                  const topologyInsideSelectablePart = topologyRow && topologyPartId && (
                    isolatedTreeRowIds?.has(topologyPartId) ||
                    focusedNodeIdSet.has(topologyPartId) ||
                    selectableNodeIdSet?.has(topologyPartId)
                  );
                  const insideIsolation = !isolatedTreeRowIds ||
                    isolatedTreeRowIds.has(rowId) ||
                    topologyInsideSelectablePart;
                  const focused = !topologyRow && focusedNodeIdSet.has(rowId);
                  const topologyWholeOfFocusedPart = (topologyType === "shape" || topologyType === "occurrence") &&
                    focusedNodeIdSet.has(String(row.node?.partId || "").trim());
                  const selectable = topologyRow
                    ? selectableTopologyRow && insideIsolation && !topologyWholeOfFocusedPart
                    : !focused && (!selectableNodeIdSet || selectableNodeIdSet.has(selectionRowId) || selected);
                  const hidden = hiddenTreeRowIds.has(String(row.id || "").trim());
                  const isolationMuted = isolateActive && !insideIsolation;
                  const rowSelectionDisabled = treeSelectionDisabled || hidden || !selectable;
                  const showSelectedRowState = selected && !hidden && !focused && !topologyWholeOfFocusedPart;
                  const hovered = !hidden && !rowSelectionDisabled && (
                    topologyRow
                      ? topologyReferenceId && normalizedHoveredReferenceId === topologyReferenceId
                      : hoveredPartId === selectionRowId
                  );
                  const rowDisabledReason = treeSelectionTitle ||
                    (!selectable
                      ? topologyWholeOfFocusedPart
                        ? "Select a face or edge of this isolated component"
                        : !topologyRow
                          ? isolateActive ? "Exit isolate to select this node" : "Select a parent assembly to inspect this node"
                          : ""
                      : "");
                  const rowHasEnabledActionButton = !topologyRow &&
                    showTreeVisibilityControls &&
                    !treeSelectionDisabled &&
                    (
                      focused
                        ? typeof onUnfocusTreeNode === "function"
                        : typeof onTogglePartVisibility === "function"
                    );
                  const rowAriaDisabled = rowSelectionDisabled && !rowHasEnabledActionButton;
                  const rowTitle = stepTreeRowTooltip(row, {
                    topologyType,
                    topologyReferenceId,
                    detail: rowDetail,
                    disabledReason: rowDisabledReason,
                  });
                  const rowDepthPx = Math.min(Math.max(row.depth, 0) * treeDepthIndentPx, treeDepthMaxPx);
                  const selectRow = (event) => {
                    const multiSelect = event.shiftKey;
                    if (topologyRow) {
                      onSelectReferenceNode?.(topologyReferenceId, { multiSelect });
                    } else {
                      onSelectTreeNode?.(selectionRowId, { multiSelect });
                    }
                  };
                  const handleRowHoverStart = () => {
                    if (rowSelectionDisabled) {
                      return;
                    }
                    if (topologyRow) {
                      if (topologyReferenceId) {
                        onHoverReferenceNode?.(topologyReferenceId);
                      }
                      return;
                    }
                    onHoverTreeNode?.(selectionRowId);
                  };
                  const handleRowHoverEnd = () => {
                    if (topologyRow) {
                      if (topologyReferenceId) {
                        onHoverReferenceNode?.("");
                      }
                      return;
                    }
                    if (!rowSelectionDisabled) {
                      onHoverTreeNode?.("");
                    }
                  };
                  const handleRowClick = (event) => {
                    if (rowSelectionDisabled) {
                      event.preventDefault();
                      return;
                    }
                    selectRow(event);
                  };
                  const handleRowKeyDown = (event) => {
                    if (event.target !== event.currentTarget || rowSelectionDisabled) {
                      return;
                    }
                    if (event.key === "ArrowDown") {
                      event.preventDefault();
                      focusTreeRowAtIndex(rowIndex + 1, 1);
                      return;
                    }
                    if (event.key === "ArrowUp") {
                      event.preventDefault();
                      focusTreeRowAtIndex(rowIndex - 1, -1);
                      return;
                    }
                    if (event.key === "Home") {
                      event.preventDefault();
                      focusTreeRowAtIndex(0, 1);
                      return;
                    }
                    if (event.key === "End") {
                      event.preventDefault();
                      focusTreeRowAtIndex(visibleRows.length - 1, -1);
                      return;
                    }
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      selectRow(event);
                      return;
                    }
                    if (rowHasChildren && event.key === "ArrowRight" && !rowExpanded) {
                      event.preventDefault();
                      onToggleTreeNode?.(row.id);
                      return;
                    }
                    if (rowHasChildren && event.key === "ArrowLeft" && rowExpanded) {
                      event.preventDefault();
                      onToggleTreeNode?.(row.id);
                    }
                  };
                  const contextFocusActionAvailable = focused
                    ? typeof onUnfocusTreeNode === "function"
                    : typeof onFocusTreeNode === "function";
                  const contextSelectDisabled = treeSelectionDisabled || (!selectable && !selected) || (hidden && !selected);
                  const contextFocusDisabled = topologyRow ||
                    treeSelectionDisabled ||
                    !contextFocusActionAvailable ||
                    (!focused && !selectable && !selected);
                  const contextExitAllIsolateAvailable = !topologyRow &&
                    isolateActive &&
                    focusedNodeIdSet.size > 1 &&
                    typeof onExitAllIsolate === "function";
                  const contextHideOtherDisabled = topologyRow ||
                    treeSelectionDisabled ||
                    hidden ||
                    typeof onHideOtherTreeNode !== "function";
                  const contextHideAllDisabled = topologyRow ||
                    treeSelectionDisabled ||
                    (hidden
                      ? typeof showAllHiddenParts !== "function"
                      : typeof hideAllParts !== "function");
                  const contextVisibilityDisabled = topologyRow ||
                    focused ||
                    !showTreeVisibilityControls ||
                    typeof onTogglePartVisibility !== "function";
                  const selectedContextNodeIds = !topologyRow
                    ? selectedIds
                      .map((id) => String(id || "").trim())
                      .filter(Boolean)
                    : [];
                  const actionNodeIds = !topologyRow
                    ? Array.from(new Set([
                      ...selectedContextNodeIds,
                      selectionRowId
                    ].filter(Boolean)))
                    : [];
                  const actionRows = actionNodeIds
                    .map((nodeId) => visibleRowById.get(nodeId) || null)
                    .filter(Boolean);
                  const collapsedActionNodeIds = actionRows
                    .filter((actionRow) => rowCanExpandOrLoad(actionRow) && !expandedTreeNodeIdSet.has(String(actionRow.id || "").trim()))
                    .map((actionRow) => String(actionRow.id || "").trim())
                    .filter(Boolean);
                  const expandedActionNodeIds = actionRows
                    .filter((actionRow) => rowCanExpandOrLoad(actionRow) && expandedTreeNodeIdSet.has(String(actionRow.id || "").trim()))
                    .map((actionRow) => String(actionRow.id || "").trim())
                    .filter(Boolean);
                  const contextActionCount = actionNodeIds.length || 1;
                  const expandSelectedDisabled = collapsedActionNodeIds.length < 1 ||
                    typeof onToggleTreeNode !== "function";
                  const collapseSelectedDisabled = expandedActionNodeIds.length < 1 ||
                    typeof onToggleTreeNode !== "function";
                  const expandAllDisabled = collapsedExpandableTreeNodeIds.length < 1 ||
                    typeof onToggleTreeNode !== "function";
                  const collapseAllDisabled = expandedExpandableTreeNodeIds.length < 1 ||
                    typeof onToggleTreeNode !== "function";
                  const copyReferenceTargetId = topologyRow ? topologyReferenceId : selectionRowId;
                  return (
                    <div key={row.id} className="relative min-w-0 max-w-full">
                      <StepTreeDepthGuides depth={row.depth} />
                      <div
                        className="relative flex h-7 min-w-0 max-w-full items-center"
                        style={rowDepthPx > 0 ? { marginLeft: `${rowDepthPx}px` } : undefined}
                      >
                        <ContextMenu modal={false}>
                          <ContextMenuTrigger asChild>
                            <div
                              ref={(node) => {
                                if (node) {
                                  rowRefs.current.set(row.id, node);
                                  if (selectionRowId && selectionRowId !== row.id) {
                                    rowRefs.current.set(selectionRowId, node);
                                  }
                                  return;
                                }
                                rowRefs.current.delete(row.id);
                                if (selectionRowId && selectionRowId !== row.id) {
                                  rowRefs.current.delete(selectionRowId);
                                }
                              }}
                              role="treeitem"
                              aria-expanded={rowHasChildren ? rowExpanded : undefined}
                              aria-selected={selected}
                              aria-label={rowAriaLabel}
                              data-step-tree-node-id={row.id || undefined}
                              data-step-tree-node-type={row.nodeType || undefined}
                              data-step-tree-topology-reference-id={topologyReferenceId || undefined}
                              data-selection-disabled={rowSelectionDisabled ? "true" : undefined}
                              aria-disabled={rowAriaDisabled}
                              tabIndex={rowSelectionDisabled ? -1 : 0}
                              className={cn(
                                "group/tree-row flex h-7 min-w-0 w-full max-w-full items-center gap-2 rounded-md px-2 outline-none transition-colors",
                                rowSelectionDisabled
                                  ? "cursor-default text-sidebar-foreground/55"
                                  : "cursor-pointer text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:bg-sidebar-accent focus-visible:text-sidebar-accent-foreground",
                                showSelectedRowState
                                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                                  : hovered && "bg-sidebar-accent text-sidebar-accent-foreground",
                                (hidden || isolationMuted) && "opacity-45"
                              )}
                              title={rowTitle}
                              onClick={handleRowClick}
                              onKeyDown={handleRowKeyDown}
                              onMouseEnter={handleRowHoverStart}
                              onMouseLeave={handleRowHoverEnd}
                            >
                              <div className="flex min-w-0 flex-1 items-center gap-1.5 overflow-hidden">
                                {rowHasChildren ? (
                                  <Button
                                    type="button"
                                    variant="ghost"
                                    size="icon-sm"
                                    className={treeChevronButtonClasses}
                                    onClick={(event) => {
                                      event.stopPropagation();
                                      onToggleTreeNode?.(row.id);
                                    }}
                                    aria-label={rowExpanded ? `Collapse ${row.label}` : `Expand ${row.label}`}
                                    title={rowExpanded ? "Collapse" : "Expand"}
                                  >
                                    <ChevronRight
                                      className={cn("size-3.5 transition-transform", rowExpanded && "rotate-90")}
                                      strokeWidth={2}
                                      aria-hidden="true"
                                    />
                                  </Button>
                                ) : null}
                                <div
                                  className={cn(
                                    treeRowContentClasses,
                                    "flex min-w-0 flex-1 shrink touch-manipulation items-center justify-start gap-1.5 overflow-hidden px-0 text-left",
                                    rowSelectionDisabled && "text-sidebar-foreground/55"
                                  )}
                                >
                                  <StepTreeRowGlyph row={row} />
                                  <span className="min-w-0 flex-1 overflow-hidden">
                                    <span className="flex min-w-0 items-baseline gap-1.5 overflow-hidden text-xs leading-4">
                                      <span className="min-w-0 truncate">
                                        {row.label}
                                      </span>
                                      {inlineRowDetail ? (
                                        <span className="min-w-0 truncate text-micro text-current/50">
                                          {inlineRowDetail}
                                        </span>
                                      ) : null}
                                    </span>
                                  </span>
                                </div>
                              </div>
                              {!topologyRow && showTreeVisibilityControls ? (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon-sm"
                                  className={cn(
                                    treeRowActionButtonClasses,
                                    "ml-1 shrink-0",
                                    !hidden && !showSelectedRowState && !hovered && !focused && "opacity-0 group-hover/tree-row:opacity-100 focus-visible:opacity-100",
                                    hidden && "text-current/75",
                                    treeSelectionDisabled && "cursor-default text-current/35 hover:!bg-transparent hover:!text-current/35"
                                  )}
                                  disabled={treeSelectionDisabled || (
                                    focused
                                      ? typeof onUnfocusTreeNode !== "function"
                                      : typeof onTogglePartVisibility !== "function"
                                  )}
                                  aria-label={focused
                                    ? `Exit isolate for ${row.label}`
                                    : hidden ? `Show ${row.label}` : `Hide ${row.label}`}
                                  title={focused ? "Exit isolate" : hidden ? "Show" : "Hide"}
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    if (focused) {
                                      onUnfocusTreeNode?.(row.id);
                                      return;
                                    }
                                    onTogglePartVisibility?.(row.id);
                                  }}
                                >
                                  {focused ? (
                                    <X className="size-3" strokeWidth={2} aria-hidden="true" />
                                  ) : hidden ? (
                                    <Eye className="size-3" strokeWidth={1.8} aria-hidden="true" />
                                  ) : (
                                    <EyeOff className="size-3" strokeWidth={1.8} aria-hidden="true" />
                                  )}
                                </Button>
                              ) : null}
                            </div>
                          </ContextMenuTrigger>
                          <ContextMenuContent className="w-44">
                        <AssemblyContextMenuItems
                          Item={ContextMenuItem}
                          Separator={ContextMenuSeparator}
                          selected={selected}
                          isolated={focused}
                          hidden={hidden}
                          actionCount={contextActionCount}
                          copyReferenceDisabled={!copyReferenceTargetId || typeof onCopyTreeNodeReference !== "function"}
                          selectDisabled={contextSelectDisabled}
                          showIsolate={!topologyRow}
                          isolateDisabled={contextFocusDisabled}
                          showExitAllIsolate={contextExitAllIsolateAvailable}
                          exitAllIsolateDisabled={treeSelectionDisabled || !contextExitAllIsolateAvailable}
                          showHideOther={!topologyRow}
                          hideOtherDisabled={contextHideOtherDisabled}
                          hideAllDisabled={contextHideAllDisabled}
                          hideAllLabel="Show all"
                          showVisibility={!topologyRow && !focused}
                          visibilityDisabled={contextVisibilityDisabled}
                          showHideAll={false}
                          showExpandCollapse={rowHasChildren || actionRows.some((actionRow) => rowCanExpandOrLoad(actionRow)) || expandableTreeNodeIds.length > 0}
                          expandSelectedDisabled={expandSelectedDisabled}
                          collapseSelectedDisabled={collapseSelectedDisabled}
                          expandAllDisabled={expandAllDisabled}
                          collapseAllDisabled={collapseAllDisabled}
                          onCopyReference={() => {
                            onCopyTreeNodeReference?.(copyReferenceTargetId, { topology: topologyRow });
                          }}
                          onSelect={(event) => {
                            if (!topologyRow && selected && selectedContextNodeIds.length > 1) {
                              onClearSelection?.();
                              return;
                            }
                            selectRow(event);
                          }}
                          onIsolate={() => {
                            if (focused) {
                              onUnfocusTreeNode?.(row.id);
                              return;
                            }
                            onFocusTreeNode?.(actionNodeIds);
                          }}
                          onExitAllIsolate={() => {
                            onExitAllIsolate?.();
                          }}
                          onHideOther={() => {
                            onHideOtherTreeNode?.(actionNodeIds);
                          }}
                          onHideAll={() => {
                            if (hidden) {
                              showAllHiddenParts?.();
                              return;
                            }
                            hideAllParts?.();
                          }}
                          onToggleVisibility={() => {
                            for (const nodeId of actionNodeIds) {
                              onTogglePartVisibility?.(nodeId);
                            }
                          }}
                          onExpandSelected={() => {
                            for (const nodeId of collapsedActionNodeIds) {
                              onToggleTreeNode?.(nodeId);
                            }
                          }}
                          onCollapseSelected={() => {
                            for (const nodeId of expandedActionNodeIds) {
                              onToggleTreeNode?.(nodeId);
                            }
                          }}
                          onExpandAll={() => {
                            for (const nodeId of collapsedExpandableTreeNodeIds) {
                              onToggleTreeNode?.(nodeId);
                            }
                          }}
                          onCollapseAll={() => {
                            for (const nodeId of expandedExpandableTreeNodeIds) {
                              onToggleTreeNode?.(nodeId);
                            }
                          }}
                        />
                          </ContextMenuContent>
                        </ContextMenu>
                      </div>
                    </div>
                  );
                })
                : null}

              {!hasAssemblyTree && !viewerLoading ? (
                <FileSheetStatusText className="py-1">
                  No assembly tree
                </FileSheetStatusText>
              ) : null}
              </div>
            </div>
      )
    },
    buildStepReferenceTab({ references: selectedReferences }),
    // Pose then Animation, directly after Reference and ahead of the readouts: they are
    // the tabs in this strip that MOVE the geometry, so they take the positions nearest
    // the default. This array is what orders the tab strip; renderedFileSheetSectionIds
    // decides which sections exist, and the two have to agree.
    //
    // Two tabs, two independent systems: one drives the mate graph, the other plays
    // choreography. Neither knows the other exists; they meet only in the viewport.
    buildPoseControlsTab({
      value: FILE_SHEET_SECTION_IDS.STEP_POSE,
      runtime: stepModule,
      loadingLabel: "Loading kinematics...",
      noParametersLabel: "No pose controls.",
      showEnableToggle: true,
      enableAriaLabel: "Enable pose",
      resetTitle: "Reset pose"
    }),
    buildAnimationControlsTab({
      value: FILE_SHEET_SECTION_IDS.STEP_ANIMATION,
      runtime: stepAnimation
    }),
    measurementsSection,
    ...themeTabs,
    // "Issues" is a diagnostic shown only when there are warnings/errors, so it trails the
    // content + display tabs as the last item in the top section (null when there are none;
    // the surface filters falsy tabs).
    buildFileStatusTab(statusItems)
  ];

  return (
    <FileSheet
      open={open}
      title="STEP"
      isDesktop={isDesktop}
      width={width}
      onOpenChange={onOpenChange}
      onStartResize={onStartResize}
      scrollBody={false}
    >
      <FileSheetTabbedSurface
        kind="step"
        sections={sections}
        openSectionIds={openSectionIds}
        onOpenSectionIdsChange={onOpenSectionIdsChange}
      />
    </FileSheet>
  );
}
