import { useEffect, useMemo, useRef } from "react";
import { ChevronRight, ClipboardPaste, Copy, Crosshair, Eye, EyeOff, Package, Pause, Play, RotateCcw } from "lucide-react";
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
const compactIconButtonClasses = "size-6 text-muted-foreground hover:text-foreground";
const treeRowButtonClasses = "h-7 min-w-0 rounded-md px-1.5 text-xs font-normal text-sidebar-foreground shadow-none hover:bg-sidebar-accent hover:text-sidebar-accent-foreground";
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

function scrollTreeNodeIntoView(target) {
  if (!target) {
    return;
  }

  const viewport = target.closest("[data-slot='scroll-area-viewport']");
  if (!viewport) {
    target.scrollIntoView?.({
      block: "nearest",
      behavior: "instant"
    });
    return;
  }

  const targetRect = target.getBoundingClientRect();
  const viewportRect = viewport.getBoundingClientRect();
  const paddedTop = viewportRect.top + treeRevealScrollPaddingTopPx;

  if (targetRect.top < paddedTop) {
    viewport.scrollTop += targetRect.top - paddedTop;
    return;
  }

  if (targetRect.bottom > viewportRect.bottom) {
    viewport.scrollTop += targetRect.bottom - viewportRect.bottom;
  }
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
  inspectedNodeId = "",
  selectableNodeIds = null,
  activeTreeNodeId: activeTreeNodeIdProp = "",
  hoveredPartId,
  hiddenPartIds,
  onSelectTreeNode,
  onToggleTreeNode,
  onInspectTreeNode,
  onClearSelection,
  onHoverTreeNode,
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
  const treeSelectClickTimerRef = useRef(null);
  const selectedIds = Array.isArray(selectedPartIds) ? selectedPartIds : [];
  const hiddenIds = Array.isArray(hiddenPartIds) ? hiddenPartIds : [];
  const normalizedInspectedNodeId = String(inspectedNodeId || "").trim();
  const selectableNodeIdSet = useMemo(() => {
    if (!Array.isArray(selectableNodeIds)) {
      return null;
    }
    return new Set(selectableNodeIds.map((id) => String(id || "").trim()).filter(Boolean));
  }, [selectableNodeIds]);
  const elideRootAssemblyRow = isAssemblyView && stepTreeNodeChildren(stepTreeRoot).length > 0;
  const rootTreeItemCount = elideRootAssemblyRow ? stepTreeNodeChildren(stepTreeRoot).length : 0;
  const rootTreeHasOverflow = rootTreeItemCount > STEP_TREE_ROOT_ITEM_LIMIT;
  const showAllRootTreeItems = !rootTreeHasOverflow || stepTreeRootShowMore === true;
  const hiddenRootTreeItemCount = Math.max(rootTreeItemCount - STEP_TREE_ROOT_ITEM_LIMIT, 0);
  const visibleRows = useMemo(
    () => flattenVisibleStepTreeRows(stepTreeRoot, expandedTreeNodeIds, {
      omitRoot: elideRootAssemblyRow,
      rootChildLimit: STEP_TREE_ROOT_ITEM_LIMIT,
      showAllRootChildren: showAllRootTreeItems
    }),
    [elideRootAssemblyRow, expandedTreeNodeIds, showAllRootTreeItems, stepTreeRoot]
  );
  const visibleRowIdsSignature = useMemo(
    () => visibleRows.map((row) => String(row?.id || "")).join("\n"),
    [visibleRows]
  );
  const hasAssemblyTree = isAssemblyView ? visibleRows.length > 0 : visibleRows.some((row) => row?.hasChildren);
  const activeTreeNodeId = String(activeTreeNodeIdProp || selectedIds[selectedIds.length - 1] || "").trim();
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
      scrollTreeNodeIntoView(rowRefs.current.get(activeTreeNodeId));
    };
    if (typeof window === "undefined") {
      scrollToActiveTreeNode();
      return;
    }
    const frameId = window.requestAnimationFrame(scrollToActiveTreeNode);
    return () => {
      window.cancelAnimationFrame(frameId);
    };
  }, [activeTreeNodeId, treeSectionOpen, visibleRowIdsSignature]);

  useEffect(() => () => {
    if (treeSelectClickTimerRef.current) {
      window.clearTimeout(treeSelectClickTimerRef.current);
      treeSelectClickTimerRef.current = null;
    }
  }, []);

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
                  const selected = selectedIds.includes(row.id);
                  const inspected = normalizedInspectedNodeId === row.id;
                  const selectable = !selectableNodeIdSet || selectableNodeIdSet.has(row.id) || selected;
                  const rowSelectionDisabled = treeSelectionDisabled || !selectable;
                  const showSelectedRowState = selected;
                  const hovered = hoveredPartId === row.id;
                  const hidden = leafIdsHidden(row.leafPartIds, hiddenIds);
                  const VisibilityIcon = hidden ? EyeOff : Eye;
                  const visibilityLabel = hidden ? "Show" : "Hide";
                  const inspectLabel = inspected ? `Exit inspection for ${row.label}` : `Inspect ${row.label}`;
                  const rowTitle = treeSelectionTitle ||
                    (selectable ? row.label : inspected ? `Inspecting ${row.label}` : "Inspect this node to select its children");
                  const rowDepthPx = Math.min(Math.max(row.depth, 0) * 24, 144);
                  return (
                    <div
                      key={row.id}
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
                      aria-current={inspected ? "true" : undefined}
                      data-selection-disabled={rowSelectionDisabled ? "true" : undefined}
                      className={cn("min-w-0 max-w-full rounded-md", hidden && "opacity-45")}
                      title={rowTitle}
                    >
                      <div className="flex h-7 min-w-0 max-w-full items-center gap-0.5">
                        <div className="flex min-w-0 flex-1 items-center gap-0 overflow-hidden" style={{ paddingLeft: rowDepthPx }}>
                          {row.hasChildren ? (
                            <Button
                              type="button"
                              variant="ghost"
                              size="icon-sm"
                              className="size-6 shrink-0 rounded-md hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
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
                          ) : null}
                          <Button
                            type="button"
                            variant="ghost"
                            size="sm"
                            className={cn(
                              treeRowButtonClasses,
                              "w-0 flex-1 touch-manipulation justify-start overflow-hidden text-left",
                              !row.hasChildren && "gap-2 !px-2",
                              rowSelectionDisabled && "text-sidebar-foreground/55",
                              showSelectedRowState
                                ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
                                : hovered && "bg-sidebar-accent text-sidebar-accent-foreground"
                            )}
                            title={rowTitle}
                            tabIndex={rowSelectionDisabled ? -1 : undefined}
                            onClick={(event) => {
                              if (rowSelectionDisabled) {
                                return;
                              }
                              const multiSelect = event.shiftKey;
                              if (treeSelectClickTimerRef.current) {
                                window.clearTimeout(treeSelectClickTimerRef.current);
                              }
                              treeSelectClickTimerRef.current = window.setTimeout(() => {
                                treeSelectClickTimerRef.current = null;
                                onSelectTreeNode?.(row.id, { multiSelect });
                              }, 180);
                            }}
                            onDoubleClick={(event) => {
                              event.preventDefault();
                              event.stopPropagation();
                              if (treeSelectClickTimerRef.current) {
                                window.clearTimeout(treeSelectClickTimerRef.current);
                                treeSelectClickTimerRef.current = null;
                              }
                              onInspectTreeNode?.(row.id);
                            }}
                            onMouseEnter={() => {
                              if (!rowSelectionDisabled) {
                                onHoverTreeNode?.(row.id);
                              }
                            }}
                            onMouseLeave={() => {
                              if (!rowSelectionDisabled) {
                                onHoverTreeNode?.("");
                              }
                            }}
                          >
                            {!row.hasChildren ? (
                              <Package className="size-3.5 shrink-0 text-sidebar-foreground/55" strokeWidth={1.8} aria-hidden="true" />
                            ) : null}
                            <span className="min-w-0 flex-1 overflow-hidden">
                              <span className="block truncate text-xs font-medium leading-4">
                                {row.label}
                              </span>
                            </span>
                          </Button>
                        </div>

                        {showTreeVisibilityControls ? (
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-sm"
                            className={cn(
                              compactIconButtonClasses,
                              "rounded-md hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                              inspected && "text-sidebar-foreground ring-1 ring-sidebar-border"
                            )}
                            onClick={(event) => {
                              event.stopPropagation();
                              onInspectTreeNode?.(row.id);
                            }}
                            aria-label={inspectLabel}
                            title={inspectLabel}
                          >
                            <Crosshair className="size-2.5" strokeWidth={2} aria-hidden="true" />
                          </Button>
                        ) : null}

                        {showTreeVisibilityControls ? (
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon-sm"
                            className={cn(
                              compactIconButtonClasses,
                              "rounded-md hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
                              hidden && "bg-sidebar-accent text-sidebar-accent-foreground"
                            )}
                            onClick={(event) => {
                              event.stopPropagation();
                              onTogglePartVisibility?.(row.id);
                            }}
                            aria-label={`${visibilityLabel} ${row.label}`}
                            title={visibilityLabel}
                          >
                            <VisibilityIcon className="size-2.5" strokeWidth={2} aria-hidden="true" />
                          </Button>
                        ) : null}
                      </div>
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
