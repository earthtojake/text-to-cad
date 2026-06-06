import { useEffect, useMemo, useRef } from "react";
import { Boxes, ChevronRight, ClipboardPaste, Copy, Eye, EyeOff, Package, Pause, Play, RotateCcw } from "lucide-react";
import { cn } from "@/ui/utils";
import {
  STEP_MODEL_ROOT_ID,
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
  ContextMenuSeparator,
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
import AssemblyContextMenuItems from "./AssemblyContextMenuItems";
import FileMetadataSection from "./FileMetadataSection";
import FileStatusSection from "./FileStatusSection";

const compactButtonClasses = FILE_SHEET_COMPACT_BUTTON_CLASSES;
const compactInputClasses = FILE_SHEET_COMPACT_INPUT_CLASSES;
const treeChevronButtonClasses = "h-7 w-4 rounded-sm px-0 text-current/60 hover:bg-sidebar-accent/45 hover:text-sidebar-accent-foreground focus-visible:bg-sidebar-accent/45";
const treeRowActionButtonClasses = "mr-1 h-5 w-5 rounded-sm px-0 text-current/60 shadow-none hover:bg-sidebar-accent/45 hover:text-sidebar-accent-foreground focus-visible:bg-sidebar-accent/45 focus-visible:text-sidebar-accent-foreground";
const treeRowContentClasses = "h-7 min-w-0 text-xs font-normal";
const treeDepthIndentPx = 16;
const treeDepthMaxPx = 128;
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

function stepTreeNodeId(node) {
  return String(node?.id || node?.occurrenceId || "").trim();
}

function expandableStepTreeNodeIds(root, { omitRoot = false } = {}) {
  if (!root) {
    return [];
  }
  const ids = [];
  const stack = [root];
  while (stack.length) {
    const node = stack.pop();
    const nodeId = stepTreeNodeId(node);
    const children = stepTreeNodeChildren(node);
    if ((!omitRoot || node !== root) && nodeId && children.length) {
      ids.push(nodeId);
    }
    for (let index = children.length - 1; index >= 0; index -= 1) {
      stack.push(children[index]);
    }
  }
  return ids;
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
  onHideOtherTreeNode,
  onToggleTreeNode,
  onClearSelection,
  onHoverTreeNode,
  onHoverReferenceNode,
  treeSelectionDisabled = false,
  treeSelectionDisabledReason = "",
  onTogglePartVisibility,
  hideSelectedParts,
  hideAllParts,
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
  const treeRootChildren = stepTreeNodeChildren(treeRoot);
  const elideRootTreeRow = treeRootChildren.length > 0 && (
    isAssemblyView ||
    stepTreeNodeId(treeRoot) === STEP_MODEL_ROOT_ID
  );
  const rootTreeItemCount = elideRootTreeRow ? treeRootChildren.length : 0;
  const rootTreeHasOverflow = rootTreeItemCount > STEP_TREE_ROOT_ITEM_LIMIT;
  const showAllRootTreeItems = !rootTreeHasOverflow || stepTreeRootShowMore === true;
  const hiddenRootTreeItemCount = Math.max(rootTreeItemCount - STEP_TREE_ROOT_ITEM_LIMIT, 0);
  const visibleRows = useMemo(
    () => flattenVisibleStepTreeRows(treeRoot, expandedTreeNodeIds, {
      omitRoot: elideRootTreeRow,
      rootChildLimit: STEP_TREE_ROOT_ITEM_LIMIT,
      showAllRootChildren: showAllRootTreeItems
    }),
    [elideRootTreeRow, expandedTreeNodeIds, showAllRootTreeItems, treeRoot]
  );
  const visibleRowIdsSignature = useMemo(
    () => visibleRows.map((row) => String(row?.id || "")).join("\n"),
    [visibleRows]
  );
  const expandableTreeNodeIds = useMemo(
    () => expandableStepTreeNodeIds(treeRoot, { omitRoot: elideRootTreeRow }),
    [elideRootTreeRow, treeRoot]
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
            <div className="max-w-full overflow-hidden px-1.5 pb-2">
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
              {viewerLoading && !visibleRows.length ? (
                <p className="px-1.5 py-2 text-xs text-[var(--ui-text-muted)]">
                  Loading STEP tree...
                </p>
              ) : null}

              {hasAssemblyTree
                ? visibleRows.map((row, rowIndex) => {
                  const topologyType = topologyTreeRowType(row);
                  const topologyRow = Boolean(topologyType);
                  const topologyReferenceId = String(row.topologyReferenceId || "").trim();
                  const selectableTopologyRow = Boolean(topologyType) &&
                    topologyReferenceId &&
                    typeof onSelectReferenceNode === "function";
                  const rowDetail = String(row.detail || "").trim();
                  const rowAriaLabel = stepTreeRowAriaLabel(row, topologyType, rowDetail);
                  const selected = topologyRow
                    ? selectedReferenceIdSet.has(topologyReferenceId)
                    : selectedIds.includes(row.id);
                  const insideIsolation = !isolatedTreeRowIds || isolatedTreeRowIds.has(String(row.id || "").trim());
                  const selectable = topologyRow
                    ? selectableTopologyRow && insideIsolation
                    : insideIsolation && (!selectableNodeIdSet || selectableNodeIdSet.has(row.id) || selected);
                  const hidden = hiddenTreeRowIds.has(String(row.id || "").trim());
                  const focused = !topologyRow && focusedNodeIdSet.has(String(row.id || "").trim());
                  const isolationMuted = isolateActive && !insideIsolation;
                  const rowSelectionDisabled = treeSelectionDisabled || hidden || !selectable;
                  const showSelectedRowState = selected && !hidden;
                  const hovered = !hidden && (
                    topologyRow
                      ? topologyReferenceId && normalizedHoveredReferenceId === topologyReferenceId
                      : hoveredPartId === row.id
                  );
                  const rowTitle = treeSelectionTitle ||
                    (topologyRow
                      ? [row.label, rowDetail].filter(Boolean).join(" - ")
                      : selectable ? row.label : isolateActive ? "Exit isolate to select this node" : "Select a parent assembly to inspect this node");
                  const rowDepthPx = Math.min(Math.max(row.depth, 0) * treeDepthIndentPx, treeDepthMaxPx);
                  const selectRow = (event) => {
                    const multiSelect = event.shiftKey;
                    if (topologyRow) {
                      onSelectReferenceNode?.(topologyReferenceId, { multiSelect });
                    } else {
                      onSelectTreeNode?.(row.id, { multiSelect });
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
                    onHoverTreeNode?.(row.id);
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
                    if (row.hasChildren && event.key === "ArrowRight" && !row.expanded) {
                      event.preventDefault();
                      onToggleTreeNode?.(row.id);
                      return;
                    }
                    if (row.hasChildren && event.key === "ArrowLeft" && row.expanded) {
                      event.preventDefault();
                      onToggleTreeNode?.(row.id);
                    }
                  };
                  const contextFocusActionAvailable = focused
                    ? typeof onUnfocusTreeNode === "function"
                    : typeof onFocusTreeNode === "function";
                  const contextSelectDisabled = treeSelectionDisabled || (!selectable && !selected) || (hidden && !selected);
                  const contextFocusDisabled = topologyRow || treeSelectionDisabled || !contextFocusActionAvailable;
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
                    !showTreeVisibilityControls ||
                    typeof onTogglePartVisibility !== "function";
                  const selectedContextNodeIds = !topologyRow && selected
                    ? selectedIds
                      .map((id) => String(id || "").trim())
                      .filter(Boolean)
                    : [];
                  const actionNodeIds = !topologyRow
                    ? (selectedContextNodeIds.length ? selectedContextNodeIds : [String(row.id || "").trim()].filter(Boolean))
                    : [];
                  const actionRows = actionNodeIds
                    .map((nodeId) => visibleRowById.get(nodeId) || null)
                    .filter(Boolean);
                  const collapsedActionNodeIds = actionRows
                    .filter((actionRow) => actionRow?.hasChildren && !expandedTreeNodeIdSet.has(String(actionRow.id || "").trim()))
                    .map((actionRow) => String(actionRow.id || "").trim())
                    .filter(Boolean);
                  const expandedActionNodeIds = actionRows
                    .filter((actionRow) => actionRow?.hasChildren && expandedTreeNodeIdSet.has(String(actionRow.id || "").trim()))
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
                  const copyReferenceTargetId = topologyRow ? topologyReferenceId : row.id;
                  return (
                    <div key={row.id} className="flex h-7 min-w-0 max-w-full items-center">
                      {rowDepthPx > 0 ? (
                        <span
                          className="h-7 shrink-0"
                          style={{
                            width: rowDepthPx,
                            minWidth: rowDepthPx
                          }}
                          aria-hidden="true"
                        />
                      ) : null}
                    <ContextMenu modal={false}>
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
                          aria-label={rowAriaLabel}
                          data-selection-disabled={rowSelectionDisabled ? "true" : undefined}
                          aria-disabled={rowSelectionDisabled}
                          tabIndex={rowSelectionDisabled ? -1 : 0}
                          className={cn(
                            "group/tree-row flex h-7 min-w-0 max-w-full flex-1 items-center rounded-sm outline-none",
                            rowSelectionDisabled
                              ? "cursor-default text-sidebar-foreground/55"
                              : "cursor-pointer text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground focus-visible:bg-sidebar-accent focus-visible:text-sidebar-accent-foreground",
                            showSelectedRowState
                              ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                              : hovered && "bg-sidebar-accent text-sidebar-accent-foreground",
                            (hidden || isolationMuted) && "opacity-45"
                          )}
                          title={rowTitle}
                          onClick={handleRowClick}
                          onKeyDown={handleRowKeyDown}
                          onMouseEnter={handleRowHoverStart}
                          onMouseLeave={handleRowHoverEnd}
                        >
                          <div className="flex min-w-0 max-w-full flex-1 items-center gap-0">
                            <div className="flex min-w-0 flex-1 overflow-hidden">
                              {row.hasChildren ? (
                                <Button
                                  type="button"
                                  variant="ghost"
                                  size="icon-sm"
                                  className={treeChevronButtonClasses}
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
                                null
                              )}
                              <div
                                className={cn(
                                  treeRowContentClasses,
                                  "flex min-w-0 flex-1 shrink touch-manipulation items-center justify-start gap-1.5 overflow-hidden px-0 text-left",
                                  rowSelectionDisabled && "text-sidebar-foreground/55"
                                )}
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
                              </div>
                            </div>
                            {!topologyRow && showTreeVisibilityControls ? (
                              <Button
                                type="button"
                                variant="ghost"
                                size="icon-sm"
                                className={cn(
                                  treeRowActionButtonClasses,
                                  "shrink-0",
                                  !hidden && !showSelectedRowState && !hovered && !focused && "opacity-0 group-hover/tree-row:opacity-100 focus-visible:opacity-100",
                                  hidden && "text-current/75",
                                  treeSelectionDisabled && "cursor-default text-current/35 hover:!bg-transparent hover:!text-current/35"
                                )}
                                disabled={treeSelectionDisabled || typeof onTogglePartVisibility !== "function"}
                                aria-label={hidden ? `Show ${row.label}` : `Hide ${row.label}`}
                                title={hidden ? "Show" : "Hide"}
                                onClick={(event) => {
                                  event.stopPropagation();
                                  onTogglePartVisibility?.(row.id);
                                }}
                              >
                                {hidden ? (
                                  <Eye className="size-3" strokeWidth={1.8} aria-hidden="true" />
                                ) : (
                                  <EyeOff className="size-3" strokeWidth={1.8} aria-hidden="true" />
                                )}
                              </Button>
                            ) : null}
                          </div>
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
                          showHideOther={!topologyRow}
                          hideOtherDisabled={contextHideOtherDisabled}
                          hideAllDisabled={contextHideAllDisabled}
                          hideAllLabel={hidden ? "Reveal all instances" : "Hide all instances"}
                          showVisibility={!topologyRow}
                          visibilityDisabled={contextVisibilityDisabled}
                          showHideAll={!topologyRow}
                          showExpandCollapse={row.hasChildren || actionRows.some((actionRow) => actionRow?.hasChildren) || expandableTreeNodeIds.length > 0}
                          expandSelectedDisabled={expandSelectedDisabled}
                          collapseSelectedDisabled={collapseSelectedDisabled}
                          expandAllDisabled={expandAllDisabled}
                          collapseAllDisabled={collapseAllDisabled}
                          onCopyReference={() => {
                            onCopyTreeNodeReference?.(copyReferenceTargetId, { topology: topologyRow });
                          }}
                          onSelect={(event) => {
                            if (!topologyRow && selectedContextNodeIds.length > 1) {
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
                            if (!hidden && selectedContextNodeIds.length > 1 && typeof hideSelectedParts === "function") {
                              hideSelectedParts();
                              return;
                            }
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
