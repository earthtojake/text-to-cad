import { useEffect, useMemo, useRef } from "react";
import { Boxes, ChevronRight, ClipboardPaste, Copy, Eye, EyeOff, Package, Pause, Play, RotateCcw } from "lucide-react";
import { cn } from "@/ui/utils";
import {
  flattenVisibleStepTreeRows,
  stepTreeNodeChildren
} from "cadjs/lib/step/stepTree";
import { resolveStepModuleNumberControlStep } from "@/workbench/stepModuleParameterControls";
import { useStepAnimationElapsed } from "@/workbench/stepAnimationStore";
import {
  Accordion
} from "../ui/accordion";
import { Button } from "../ui/button";
import {
  ContextMenu,
  ContextMenuContent,
  ContextMenuItem,
  ContextMenuTrigger
} from "../ui/context-menu";
import { ColorPicker } from "../ui/color-picker";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "../ui/select";
import { Slider } from "../ui/slider";
import FileSheet, {
  FILE_SHEET_COMPACT_BUTTON_CLASSES,
  FILE_SHEET_COMPACT_INPUT_CLASSES,
  FILE_SHEET_PRECISION_SLIDER_CLASSES,
  FileSheetControlRow,
  FileSheetSection,
  FileSheetSectionBody,
  FileSheetSliderField,
  FileSheetSubsection,
  FileSheetToggleRow,
  parseFileSheetNumberInput
} from "./FileSheet";
import FileMetadataSection from "./FileMetadataSection";
import FileStatusSection from "./FileStatusSection";

const compactButtonClasses = FILE_SHEET_COMPACT_BUTTON_CLASSES;
const compactInputClasses = FILE_SHEET_COMPACT_INPUT_CLASSES;
const treeActionButtonClasses = "h-7 w-6 rounded-sm text-muted-foreground hover:text-foreground";
const treeChevronButtonClasses = "h-7 rounded-sm px-0 pr-1 text-muted-foreground hover:text-sidebar-accent-foreground";
const treeRowButtonClasses = "h-7 min-w-0 rounded-sm px-0 text-xs font-normal text-sidebar-foreground shadow-none hover:bg-sidebar-accent hover:text-sidebar-accent-foreground";
const treeSectionId = "tree";
const treeRevealScrollPaddingTopPx = 120;
export const STEP_TREE_ROOT_ITEM_LIMIT = 15;
const STEP_MODULE_ANIMATION_SPEED_MIN = 0.1;
const STEP_MODULE_ANIMATION_SPEED_MAX = 3;

function formatControlNumber(value) {
  const numericValue = Number(value);
  if (!Number.isFinite(numericValue)) {
    return "0";
  }
  if (Math.abs(numericValue) >= 100) {
    return numericValue.toFixed(0);
  }
  if (Math.abs(numericValue) >= 10) {
    return numericValue.toFixed(1);
  }
  return numericValue.toFixed(2);
}

function formatSeconds(value) {
  const numericValue = Math.max(Number(value) || 0, 0);
  return `${numericValue.toFixed(numericValue >= 10 ? 1 : 2)}s`;
}

function parseAnimationSpeedInput(value, fallbackValue = 1) {
  return parseFileSheetNumberInput(value, {
    fallback: fallbackValue,
    min: STEP_MODULE_ANIMATION_SPEED_MIN,
    max: STEP_MODULE_ANIMATION_SPEED_MAX
  });
}

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

function TopologySvg({ children }) {
  return (
    <svg
      className="size-3.5 shrink-0 text-sidebar-foreground/55"
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
  const common = "relative size-3.5 shrink-0 text-sidebar-foreground/55";
  if (normalizedType === "occurrence") {
    return (
      <span className={common} aria-hidden="true">
        <span className="absolute left-0.5 top-1 size-2.5 rounded-[2px] border border-current" />
        <span className="absolute right-0 top-0 size-2 rounded-[2px] border border-current bg-sidebar" />
      </span>
    );
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
  if (topologyType) {
    return <TopologyTreeGlyph row={row} type={topologyType} />;
  }
  const nodeType = String(row?.nodeType || row?.node?.nodeType || "").trim();
  const iconClasses = "size-3.5 shrink-0 text-sidebar-foreground/55";
  if (nodeType === "assembly") {
    return <Boxes className={iconClasses} strokeWidth={1.8} aria-hidden="true" />;
  }
  return <Package className={iconClasses} strokeWidth={1.8} aria-hidden="true" />;
}

function StepModuleAnimationTimeControl({
  animationState,
  duration,
  enabled,
  onScrub
}) {
  const liveElapsedSec = useStepAnimationElapsed();
  const rawElapsedSec = animationState?.playing
    ? liveElapsedSec
    : Number(animationState?.elapsedSec) || 0;
  const elapsedSec = Math.min(Math.max(rawElapsedSec, 0), duration);

  return (
    <FileSheetSliderField
      label="Time"
      value={formatSeconds(elapsedSec)}
      onValueCommit={(nextValue) => {
        onScrub?.(parseFileSheetNumberInput(nextValue, {
          fallback: elapsedSec,
          min: 0,
          max: duration
        }));
      }}
      valueInputProps={{
        disabled: !enabled,
        ariaLabel: "STEP animation time value"
      }}
    >
      <Slider
        className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
        value={[elapsedSec]}
        min={0}
        max={duration}
        step={0.01}
        onValueChange={(nextValue) => onScrub?.(nextValue?.[0] ?? 0)}
        disabled={!enabled}
        aria-label="STEP animation time"
      />
    </FileSheetSliderField>
  );
}

export default function StepFileSheet({
  open,
  isDesktop,
  width,
  onOpenChange,
  onStartResize,
  selectedEntry,
  viewerLoading,
  isAssemblyView = false,
  stepTreeRoot,
  expandedTreeNodeIds,
  stepTreeRootShowMore = false,
  onStepTreeRootShowMoreChange,
  selectedPartIds,
  selectedReferenceIds = [],
  selectableNodeIds = null,
  activeTreeNodeId: activeTreeNodeIdProp = "",
  hoveredPartId,
  hoveredReferenceId = "",
  hiddenPartIds,
  focusedNodeIds = [],
  onSelectTreeNode,
  onSelectReferenceNode,
  onCopyTreeNodeReference,
  onFocusTreeNode,
  onUnfocusTreeNode,
  onToggleTreeNode,
  onClearSelection,
  onHoverTreeNode,
  onHoverReferenceNode,
  treeSelectionDisabled = false,
  treeSelectionDisabledReason = "",
  onTogglePartVisibility,
  hideSelectedParts,
  showAllHiddenParts,
  stepModule = null,
  fileDownloadAvailable = false,
  viewerServerInfo = null,
  localFileOpenAvailable = false,
  fileAccessBusyKey = "",
  onOpenFileAsset,
  suppressDynamicMetadataStatus = false,
  statusItems = [],
  themeSections = null,
  openSectionIds = [],
  onOpenSectionIdsChange
}) {
  const rowRefs = useRef(new Map());
  const selectedIds = Array.isArray(selectedPartIds) ? selectedPartIds : [];
  const selectedReferenceIdSet = useMemo(
    () => new Set((Array.isArray(selectedReferenceIds) ? selectedReferenceIds : []).map((id) => String(id || "").trim()).filter(Boolean)),
    [selectedReferenceIds]
  );
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
  const elideRootAssemblyRow = isAssemblyView && stepTreeNodeChildren(treeRoot).length > 0;
  const rootTreeItemCount = elideRootAssemblyRow ? stepTreeNodeChildren(treeRoot).length : 0;
  const rootTreeHasOverflow = rootTreeItemCount > STEP_TREE_ROOT_ITEM_LIMIT;
  const showAllRootTreeItems = !rootTreeHasOverflow || stepTreeRootShowMore === true;
  const hiddenRootTreeItemCount = Math.max(rootTreeItemCount - STEP_TREE_ROOT_ITEM_LIMIT, 0);
  const visibleRows = useMemo(
    () => flattenVisibleStepTreeRows(treeRoot, expandedTreeNodeIds, {
      omitRoot: elideRootAssemblyRow,
      rootChildLimit: STEP_TREE_ROOT_ITEM_LIMIT,
      showAllRootChildren: showAllRootTreeItems
    }),
    [elideRootAssemblyRow, expandedTreeNodeIds, showAllRootTreeItems, treeRoot]
  );
  const visibleRowIdsSignature = useMemo(
    () => visibleRows.map((row) => String(row?.id || "")).join("\n"),
    [visibleRows]
  );
  const hiddenTreeRowIds = useMemo(
    () => hiddenStepTreeRowIds(visibleRows, hiddenIds),
    [hiddenIds, visibleRows]
  );
  const hasAssemblyTree = isAssemblyView ? visibleRows.length > 0 : visibleRows.some((row) => row?.hasChildren);
  const activeSelectedReferenceId = String(
    Array.isArray(selectedReferenceIds) ? selectedReferenceIds[selectedReferenceIds.length - 1] || "" : ""
  ).trim();
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
      ? visibleRows.find((row) => String(row?.id || "").trim() === activeTreeNodeId) || null
      : null,
    [activeTreeNodeId, visibleRows]
  );
  const activeTreeNodeIsTopology = Boolean(topologyTreeRowType(activeTreeRow));
  const selectedPartCount = selectedIds.length;
  const hiddenPartCount = hiddenIds.length;
  const showTreeVisibilityControls = isAssemblyView === true;
  const treeSectionOpen = Array.isArray(openSectionIds) && openSectionIds.includes(treeSectionId);
  const treeSelectionTitle = treeSelectionDisabled
    ? String(treeSelectionDisabledReason || "Tree selection is disabled in the current parameter state.").trim()
    : "";
  const stepModuleDefinition = stepModule?.definition || null;
  const stepModuleParameters = Array.isArray(stepModuleDefinition?.parameters) ? stepModuleDefinition.parameters : [];
  const stepModuleAnimations = Array.isArray(stepModuleDefinition?.animations) ? stepModuleDefinition.animations : [];
  const stepModuleStatus = String(stepModule?.status || "").trim();
  const stepModuleError = String(stepModule?.error || "").trim();
  const stepModuleValues = stepModule?.parameterValues || {};
  const stepModuleAnimationState = stepModule?.animationState || {};
  const stepModuleAnimationDuration = Math.max(Number(stepModuleAnimationState.duration) || 1, 0.001);
  const stepModuleEnabled = stepModule?.enabled !== false;

  useEffect(() => {
    if (!activeTreeNodeId || !treeSectionOpen) {
      return;
    }
    const scrollToActiveTreeNode = () => {
      scrollTreeNodeIntoView(rowRefs.current.get(activeTreeNodeId), {
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
  }, [activeTreeNodeId, activeTreeNodeIsTopology, treeSectionOpen, visibleRowIdsSignature]);

  if (!selectedEntry) {
    return null;
  }

  return (
    <FileSheet
      open={open}
      title="STEP"
      isDesktop={isDesktop}
      width={width}
      onOpenChange={onOpenChange}
      onStartResize={onStartResize}
    >
      <Accordion
        type="multiple"
        value={openSectionIds}
        onValueChange={onOpenSectionIdsChange}
      >
        <FileStatusSection items={statusItems} />

        <FileSheetSection
          value={treeSectionId}
          title="Tree"
          triggerProps={{ title: treeSelectionTitle || undefined }}
        >
            {showTreeVisibilityControls ? (
              <div className="space-y-1.5 px-3 py-1.5">
                <div className="flex flex-wrap gap-1.5">
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className={compactButtonClasses}
                    onClick={hideSelectedParts}
                    disabled={treeSelectionDisabled || selectedPartCount < 2}
                    title={treeSelectionDisabled ? treeSelectionTitle : selectedPartCount > 1 ? `Hide ${selectedPartCount} selected nodes` : "Select multiple nodes to hide them together"}
                  >
                    <EyeOff className="size-3" strokeWidth={2} aria-hidden="true" />
                    <span>Hide all</span>
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className={compactButtonClasses}
                    onClick={showAllHiddenParts}
                    disabled={hiddenPartCount < 1}
                    title={hiddenPartCount > 0 ? `Show ${hiddenPartCount} hidden ${hiddenPartCount === 1 ? "part" : "parts"}` : "No hidden parts to show"}
                  >
                    <Eye className="size-3" strokeWidth={2} aria-hidden="true" />
                    <span>Show all</span>
                  </Button>
                </div>
              </div>
            ) : null}

            <div className="max-w-full overflow-hidden px-1.5 pb-2">
              <div
                className="space-y-px"
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
              {viewerLoading && !visibleRows.length ? (
                <p className="px-1.5 py-2 text-xs text-[var(--ui-text-muted)]">
                  Loading STEP tree...
                </p>
              ) : null}

              {hasAssemblyTree
                ? visibleRows.map((row) => {
                  const topologyType = topologyTreeRowType(row);
                  const topologyRow = Boolean(topologyType);
                  const topologyReferenceId = String(row.topologyReferenceId || "").trim();
                  const selectableTopologyRow = Boolean(topologyType) &&
                    topologyReferenceId &&
                    typeof onSelectReferenceNode === "function";
                  const rowDetail = String(row.detail || "").trim();
                  const selected = topologyRow
                    ? selectedReferenceIdSet.has(topologyReferenceId)
                    : selectedIds.includes(row.id);
                  const selectable = topologyRow
                    ? selectableTopologyRow
                    : (!selectableNodeIdSet || selectableNodeIdSet.has(row.id) || selected);
                  const hidden = hiddenTreeRowIds.has(String(row.id || "").trim());
                  const focused = !topologyRow && focusedNodeIdSet.has(String(row.id || "").trim());
                  const rowSelectionDisabled = treeSelectionDisabled || hidden || !selectable;
                  const showSelectedRowState = selected && !hidden;
                  const hovered = !hidden && (
                    topologyRow
                      ? topologyReferenceId && normalizedHoveredReferenceId === topologyReferenceId
                      : hoveredPartId === row.id
                  );
                  const VisibilityIcon = hidden ? EyeOff : Eye;
                  const visibilityLabel = hidden ? "Show" : "Hide";
                  const primaryLabel = `Select ${row.label}`;
                  const rowTitle = treeSelectionTitle ||
                    (topologyRow
                      ? [row.label, rowDetail].filter(Boolean).join(" - ")
                      : selectable ? row.label : "Focus this node to select its children");
                  const rowDepthPx = Math.min(Math.max(row.depth, 0) * 18, 132);
                  const chevronButtonWidthPx = rowDepthPx + 20;
                  const selectRow = (event) => {
                    const multiSelect = event.shiftKey;
                    if (topologyRow) {
                      onSelectReferenceNode?.(topologyReferenceId, { multiSelect });
                    } else {
                      onSelectTreeNode?.(row.id, { multiSelect });
                    }
                  };
                  const contextFocusLabel = focused ? "Unfocus" : "Focus";
                  const contextFocusActionAvailable = focused
                    ? typeof onUnfocusTreeNode === "function"
                    : typeof onFocusTreeNode === "function";
                  const contextSelectDisabled = treeSelectionDisabled || (!selectable && !selected) || (hidden && !selected);
                  const contextFocusDisabled = topologyRow || treeSelectionDisabled || !contextFocusActionAvailable;
                  const contextVisibilityDisabled = topologyRow ||
                    !showTreeVisibilityControls ||
                    typeof onTogglePartVisibility !== "function";
                  const copyReferenceTargetId = topologyRow ? topologyReferenceId : row.id;
                  return (
                    <ContextMenu key={row.id} modal={false}>
                      <ContextMenuTrigger asChild>
                        <div
                          ref={(node) => {
                            if (node) {
                              rowRefs.current.set(row.id, node);
                              return;
                            }
                            rowRefs.current.delete(row.id);
                          }}
                          role="treeitem"
                          aria-expanded={row.hasChildren ? row.expanded : undefined}
                          aria-selected={selected}
                          data-selection-disabled={rowSelectionDisabled ? "true" : undefined}
                          className={cn("min-w-0 max-w-full rounded-sm", hidden && "opacity-45")}
                          title={rowTitle}
                        >
                          <div className="flex h-7 min-w-0 max-w-full items-center gap-0">
                            <div className="flex min-w-0 flex-1 overflow-hidden">
                              {row.hasChildren ? (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon-sm"
                                  className={cn(
                                    treeChevronButtonClasses,
                                    "justify-end hover:bg-sidebar-accent"
                                  )}
                                  style={{
                                    width: chevronButtonWidthPx,
                                    minWidth: chevronButtonWidthPx
                                  }}
                                  onClick={(event) => {
                                    event.stopPropagation();
                                    onToggleTreeNode?.(row.id);
                                  }}
                                  aria-label={row.expanded ? `Collapse ${row.label}` : `Expand ${row.label}`}
                                  title={row.expanded ? "Collapse" : "Expand"}
                                >
                                  <ChevronRight
                                    className={cn("size-3.5 transition-transform", row.expanded && "rotate-90")}
                                    strokeWidth={2}
                                    aria-hidden="true"
                                  />
                                </Button>
                              ) : (
                                <span
                                  className="h-7 shrink-0"
                                  style={{
                                    width: chevronButtonWidthPx,
                                    minWidth: chevronButtonWidthPx
                                  }}
                                  aria-hidden="true"
                                />
                              )}
                              <Button
                                type="button"
                                variant="ghost"
                                size="sm"
                                className={cn(
                                  treeRowButtonClasses,
                                  "min-w-0 flex-1 shrink touch-manipulation justify-start gap-1 overflow-hidden !px-1 text-left",
                                  rowSelectionDisabled && "text-sidebar-foreground/55",
                                  showSelectedRowState
                                    ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                                    : hovered && "bg-sidebar-accent text-sidebar-accent-foreground"
                                )}
                                title={rowTitle}
                                aria-label={primaryLabel}
                                tabIndex={rowSelectionDisabled ? -1 : undefined}
                                disabled={rowSelectionDisabled}
                                onClick={(event) => {
                                  if (rowSelectionDisabled) {
                                    return;
                                  }
                                  selectRow(event);
                                }}
                                onMouseEnter={() => {
                                  if (topologyRow) {
                                    if (!treeSelectionDisabled && topologyReferenceId) {
                                      onHoverReferenceNode?.(topologyReferenceId);
                                    }
                                    return;
                                  }
                                  if (!rowSelectionDisabled) {
                                    onHoverTreeNode?.(row.id);
                                  }
                                }}
                                onMouseLeave={() => {
                                  if (topologyRow) {
                                    if (topologyReferenceId) {
                                      onHoverReferenceNode?.("");
                                    }
                                    return;
                                  }
                                  if (!rowSelectionDisabled) {
                                    onHoverTreeNode?.("");
                                  }
                                }}
                              >
                                <StepTreeRowGlyph row={row} />
                                <span className="min-w-0 flex-1 overflow-hidden">
                                  <span className="flex min-w-0 items-baseline gap-1.5 overflow-hidden text-xs font-medium leading-4">
                                    <span className="min-w-0 truncate">
                                      {row.label}
                                    </span>
                                    {rowDetail ? (
                                      <span className="min-w-0 truncate text-[10px] font-normal text-sidebar-foreground/50">
                                        {rowDetail}
                                      </span>
                                    ) : null}
                                  </span>
                                </span>
                              </Button>
                            </div>

                            {showTreeVisibilityControls && !topologyRow ? (
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon-sm"
                                className={cn(
                                  treeActionButtonClasses,
                                  "hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                                  hidden && "bg-sidebar-accent text-sidebar-accent-foreground"
                                )}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  onTogglePartVisibility?.(row.id);
                                }}
                                aria-label={`${visibilityLabel} ${row.label}`}
                                title={visibilityLabel}
                              >
                                <VisibilityIcon className="size-3" strokeWidth={2} aria-hidden="true" />
                              </Button>
                            ) : null}
                          </div>
                        </div>
                      </ContextMenuTrigger>
                      <ContextMenuContent className="w-44">
                        <ContextMenuItem
                          className="text-xs"
                          disabled={!copyReferenceTargetId || typeof onCopyTreeNodeReference !== "function"}
                          onSelect={() => {
                            onCopyTreeNodeReference?.(copyReferenceTargetId, { topology: topologyRow });
                          }}
                        >
                          <span className="min-w-0 truncate">Copy Reference</span>
                        </ContextMenuItem>
                        <ContextMenuItem
                          className="text-xs"
                          disabled={contextSelectDisabled}
                          onSelect={(event) => {
                            selectRow(event);
                          }}
                        >
                          <span className="min-w-0 truncate">{selected ? "Deselect" : "Select"}</span>
                        </ContextMenuItem>
                        <ContextMenuItem
                          className="text-xs"
                          disabled={contextFocusDisabled}
                          onSelect={() => {
                            if (focused) {
                              onUnfocusTreeNode?.(row.id);
                              return;
                            }
                            onFocusTreeNode?.(row.id);
                          }}
                        >
                          <span className="min-w-0 truncate">{contextFocusLabel}</span>
                        </ContextMenuItem>
                        <ContextMenuItem
                          className="text-xs"
                          disabled={contextVisibilityDisabled}
                          onSelect={() => {
                            onTogglePartVisibility?.(row.id);
                          }}
                        >
                          <span className="min-w-0 truncate">{hidden ? "Reveal" : "Hide"}</span>
                        </ContextMenuItem>
                      </ContextMenuContent>
                    </ContextMenu>
                  );
                })
                : null}

              {!hasAssemblyTree && !viewerLoading ? (
                <p className="px-1.5 py-2 text-xs text-[var(--ui-text-muted)]">
                  No assembly tree
                </p>
              ) : null}
              </div>

              {rootTreeHasOverflow ? (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className={cn(
                    compactButtonClasses,
                    "mt-1 h-7 w-full justify-start rounded-md px-2 text-[11px] text-sidebar-foreground/70 hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
                  )}
                  onClick={() => {
                    onStepTreeRootShowMoreChange?.(!showAllRootTreeItems);
                  }}
                  aria-expanded={showAllRootTreeItems}
                  title={showAllRootTreeItems
                    ? `Show first ${STEP_TREE_ROOT_ITEM_LIMIT} root items`
                    : `Show ${hiddenRootTreeItemCount} more root ${hiddenRootTreeItemCount === 1 ? "item" : "items"}`}
                >
                  <span>{showAllRootTreeItems ? "Show less" : "Show more"}</span>
                </Button>
              ) : null}
            </div>
        </FileSheetSection>

        {stepModuleDefinition || stepModuleStatus === "loading" || stepModuleError ? (
          <FileSheetSection value="parameters" title="Parameters">
              <FileSheetSectionBody>
                {stepModuleDefinition ? (
                  <FileSheetToggleRow
                    label="Enable"
                    checked={stepModuleEnabled}
                    onCheckedChange={(checked) => stepModule?.onEnabledChange?.(checked)}
                    ariaLabel="Enable STEP module"
                  />
                ) : null}

                {stepModuleStatus === "loading" ? (
                  <p className="px-3 py-2 text-xs text-[var(--ui-text-muted)]">Loading STEP module...</p>
                ) : null}
                {stepModuleError ? (
                  <p className="whitespace-pre-line px-3 py-2 text-xs text-destructive">{stepModuleError}</p>
                ) : null}

                {stepModuleDefinition && stepModuleAnimations.length ? (
                  <>
                    {stepModuleAnimations.length > 1 ? (
                      <FileSheetControlRow label="Animation">
                        <Select
                          value={String(stepModuleAnimationState.activeId || stepModuleAnimations[0]?.id || "")}
                          onValueChange={(nextValue) => stepModule?.onAnimationSelect?.(nextValue)}
                          disabled={!stepModuleEnabled}
                        >
                          <SelectTrigger size="sm" className="h-7 !text-[11px]" aria-label="STEP animation">
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {stepModuleAnimations.map((animation) => (
                              <SelectItem key={animation.id} value={animation.id}>
                                {animation.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </FileSheetControlRow>
                    ) : null}
                    <FileSheetControlRow>
                      <div className="grid grid-cols-2 gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className={cn(compactButtonClasses, "justify-center")}
                          onClick={() => stepModule?.onAnimationPlayToggle?.()}
                          disabled={!stepModuleEnabled}
                        >
                          {stepModuleAnimationState.playing ? (
                            <Pause className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                          ) : (
                            <Play className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                          )}
                          <span>{stepModuleAnimationState.playing ? "Pause" : "Play"}</span>
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className={cn(compactButtonClasses, "justify-center")}
                          onClick={() => stepModule?.onAnimationReset?.()}
                          disabled={!stepModuleEnabled}
                          aria-label="Restart STEP animation"
                          title="Restart"
                        >
                          <RotateCcw className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                          <span>Reset</span>
                        </Button>
                      </div>
                    </FileSheetControlRow>
                    <StepModuleAnimationTimeControl
                      animationState={stepModuleAnimationState}
                      duration={stepModuleAnimationDuration}
                      enabled={stepModuleEnabled}
                      onScrub={stepModule?.onAnimationScrub}
                    />
                    <FileSheetSliderField
                      label="Speed"
                      value={`${formatControlNumber(stepModuleAnimationState.speed || 1)}x`}
                      onValueCommit={(nextValue) => {
                        stepModule?.onAnimationSpeedChange?.(
                          parseAnimationSpeedInput(nextValue, stepModuleAnimationState.speed || 1)
                        );
                      }}
                      valueInputProps={{
                        disabled: !stepModuleEnabled,
                        ariaLabel: "STEP animation speed value"
                      }}
                    >
                      <Slider
                        className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
                        value={[Number(stepModuleAnimationState.speed) || 1]}
                        min={STEP_MODULE_ANIMATION_SPEED_MIN}
                        max={STEP_MODULE_ANIMATION_SPEED_MAX}
                        step={0.1}
                        onValueChange={(nextValue) => stepModule?.onAnimationSpeedChange?.(nextValue?.[0] ?? 1)}
                        disabled={!stepModuleEnabled}
                        aria-label="STEP animation speed"
                      />
                    </FileSheetSliderField>
                  </>
                ) : null}

                {stepModuleDefinition && !stepModuleParameters.length ? (
                  <p className="px-3 py-2 text-xs text-[var(--ui-text-muted)]">No module parameters.</p>
                ) : null}
                {stepModuleParameters.map((parameter) => {
                  const value = stepModuleValues?.[parameter.id] ?? parameter.defaultValue;
                  const controlStep = resolveStepModuleNumberControlStep(parameter);
                  if (parameter.type === "boolean") {
                    return (
                      <FileSheetToggleRow
                        key={parameter.id}
                        label={parameter.label}
                        checked={value === true}
                        onCheckedChange={(checked) => stepModule?.onParameterChange?.(parameter.id, checked)}
                        disabled={!stepModuleEnabled}
                        ariaLabel={parameter.label}
                      />
                    );
                  }
                  if (parameter.type === "enum") {
                    return (
                      <FileSheetControlRow key={parameter.id} label={parameter.label}>
                        <Select
                          value={String(value ?? "")}
                          onValueChange={(nextValue) => stepModule?.onParameterChange?.(parameter.id, nextValue)}
                          disabled={!stepModuleEnabled}
                        >
                          <SelectTrigger size="sm" className="h-7 !text-[11px]" aria-label={parameter.label}>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {parameter.options.map((option) => (
                              <SelectItem key={option.value} value={option.value}>
                                {option.label}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      </FileSheetControlRow>
                    );
                  }
                  if (parameter.type === "color") {
                    return (
                      <FileSheetControlRow
                        key={parameter.id}
                        label={parameter.label}
                        trailing={(
                          <ColorPicker
                            value={String(value || "#ffffff")}
                            onChange={(nextValue) => stepModule?.onParameterChange?.(parameter.id, nextValue)}
                            disabled={!stepModuleEnabled}
                            className={cn(compactInputClasses, "w-fit justify-start gap-1.5 px-1.5")}
                            swatchClassName="size-3.5"
                            popoverAlign="end"
                            aria-label={parameter.label}
                          />
                        )}
                      />
                    );
                  }
                  if (parameter.type === "button") {
                    return (
                      <FileSheetControlRow key={parameter.id}>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          className={cn(compactButtonClasses, "w-full justify-center")}
                          onClick={() => stepModule?.onParameterChange?.(parameter.id, Number(value || 0) + 1)}
                          disabled={!stepModuleEnabled}
                        >
                          {parameter.label}
                        </Button>
                      </FileSheetControlRow>
                    );
                  }
                  return (
                    <FileSheetSliderField
                      key={parameter.id}
                      label={parameter.label}
                      value={`${formatControlNumber(value)}${parameter.unit ? ` ${parameter.unit}` : ""}`}
                      onValueCommit={(nextValue) => {
                        stepModule?.onParameterChange?.(parameter.id, parseFileSheetNumberInput(nextValue, {
                          fallback: value,
                          min: parameter.min,
                          max: parameter.max
                        }));
                      }}
                      valueInputProps={{
                        disabled: !stepModuleEnabled,
                        ariaLabel: `${parameter.label} slider value`
                      }}
                    >
                      <Slider
                        className={FILE_SHEET_PRECISION_SLIDER_CLASSES}
                        value={[Number(value) || 0]}
                        min={parameter.min}
                        max={parameter.max}
                        step={controlStep}
                        onValueChange={(nextValue) => stepModule?.onParameterChange?.(parameter.id, nextValue?.[0] ?? value)}
                        disabled={!stepModuleEnabled}
                        aria-label={parameter.label}
                      />
                    </FileSheetSliderField>
                  );
                })}
                {stepModuleDefinition && stepModuleParameters.length ? (
                  <FileSheetControlRow className="pt-2">
                    <div className="grid grid-cols-2 gap-2">
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className={cn(compactButtonClasses, "justify-center")}
                        onClick={() => {
                          void stepModule?.onCopyParams?.();
                        }}
                        title="Copy STEP parameter JSON"
                      >
                        <Copy className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                        <span>Copy parameters</span>
                      </Button>
                      <Button
                        type="button"
                        variant="outline"
                        size="sm"
                        className={cn(compactButtonClasses, "justify-center")}
                        onClick={() => {
                          void stepModule?.onPasteParams?.();
                        }}
                        title="Paste STEP parameter JSON"
                      >
                        <ClipboardPaste className="h-3.5 w-3.5" strokeWidth={2} aria-hidden="true" />
                        <span>Paste parameters</span>
                      </Button>
                    </div>
                  </FileSheetControlRow>
                ) : null}
              </FileSheetSectionBody>
          </FileSheetSection>
        ) : null}

        {themeSections}
        <FileMetadataSection
          entry={selectedEntry}
          fileDownloadAvailable={fileDownloadAvailable}
          viewerServerInfo={viewerServerInfo}
          localFileOpenAvailable={localFileOpenAvailable}
          fileAccessBusyKey={fileAccessBusyKey}
          onOpenFileAsset={onOpenFileAsset}
          suppressDynamicStatus={suppressDynamicMetadataStatus}
        />
      </Accordion>
    </FileSheet>
  );
}
