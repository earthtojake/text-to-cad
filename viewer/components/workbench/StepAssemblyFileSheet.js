import { useEffect, useMemo, useRef, useState } from "react";
import { ChevronLeft, Expand, Eye, EyeOff } from "lucide-react";
import { cn } from "../../lib/cn";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger
} from "../ui/accordion";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import FileSheet from "./FileSheet";

const fieldLabelClasses = "block text-xs font-medium text-muted-foreground";
const compactButtonClasses = "h-8 px-2 text-xs";
const compactIconButtonClasses = "size-8";
const compactInputClasses = "h-8 text-[11px] md:text-[11px] placeholder:text-[11px]";

export default function StepAssemblyFileSheet({
  open,
  isDesktop,
  width,
  selectedEntry,
  viewerLoading,
  isAssemblyView,
  assemblyParts,
  filteredAssemblyParts,
  selectedPartIds,
  hoveredPartId,
  hiddenPartIds,
  partLabelsVisible,
  setPartLabelsVisible,
  togglePartSelection,
  clearAssemblySelection,
  setHoveredListPartId,
  handleInspectAssemblyPart,
  handleBackAssemblyInspection,
  togglePartVisibility,
  hideSelectedParts,
  showAllHiddenParts,
  handleExitAssemblyPartInspection,
  inspectedAssemblyPart,
  assemblyBreadcrumbNodes
}) {
  const [partQuery, setPartQuery] = useState("");
  const partCount = Array.isArray(assemblyParts) ? assemblyParts.length : 0;
  const filteredParts = Array.isArray(filteredAssemblyParts) ? filteredAssemblyParts : [];
  const normalizedPartQuery = partQuery.trim().toLowerCase();
  const visibleAssemblyParts = useMemo(() => {
    if (!normalizedPartQuery) {
      return filteredParts;
    }
    return filteredParts.filter((part) => {
      const name = String(part?.name || "").toLowerCase();
      const label = String(part?.label || "").toLowerCase();
      const id = String(part?.id || "").toLowerCase();
      return name.includes(normalizedPartQuery) || label.includes(normalizedPartQuery) || id.includes(normalizedPartQuery);
    });
  }, [filteredParts, normalizedPartQuery]);
  const selectedPartCount = Array.isArray(selectedPartIds) ? selectedPartIds.length : 0;
  const hiddenPartCount = Array.isArray(hiddenPartIds) ? hiddenPartIds.length : 0;
  const breadcrumbNodes = Array.isArray(assemblyBreadcrumbNodes) ? assemblyBreadcrumbNodes : [];
  const canGoBack = breadcrumbNodes.length > 1;
  const isInspectingLeafPart = String(inspectedAssemblyPart?.nodeType || "").trim() === "part";
  const showBackButton = canGoBack || isInspectingLeafPart;
  const showHideAllAction = selectedPartCount > 1;
  const showShowAllAction = hiddenPartCount > 1;
  const partRowRefs = useRef(new Map());
  const activePartId = inspectedAssemblyPart?.id || selectedPartIds[selectedPartIds.length - 1] || "";

  useEffect(() => {
    if (!activePartId) {
      return;
    }
    const target = partRowRefs.current.get(activePartId);
    target?.scrollIntoView?.({
      block: "nearest"
    });
  }, [activePartId]);

  if (!selectedEntry || !isAssemblyView) {
    return null;
  }

  return (
    <FileSheet
      open={open}
      title="Assembly"
      isDesktop={isDesktop}
      width={width}
    >
      <Accordion type="multiple" defaultValue={["parts"]}>
        <AccordionItem value="parts">
          <AccordionTrigger>Parts</AccordionTrigger>
          <AccordionContent>
            <div className="space-y-1.5 px-3 py-2">
              {showBackButton ? (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className={compactButtonClasses}
                  onClick={canGoBack ? handleBackAssemblyInspection : handleExitAssemblyPartInspection}
                  title={canGoBack ? "Back to parent assembly" : "Exit part inspection"}
                >
                  <ChevronLeft className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
                  <span>Back</span>
                </Button>
              ) : null}
              <label className="block">
                <span className={fieldLabelClasses}>Filter</span>
                <Input
                  type="search"
                  className={`${compactInputClasses} mt-1.5`}
                  placeholder="Parts"
                  aria-label="Filter parts"
                  value={partQuery}
                  onChange={(event) => setPartQuery(event.target.value)}
                />
              </label>
              <div className="flex flex-wrap gap-1.5">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className={compactButtonClasses}
                  onClick={hideSelectedParts}
                  disabled={!showHideAllAction}
                  title={showHideAllAction ? `Hide ${selectedPartCount} selected parts` : "Select multiple parts to hide them together"}
                >
                  <EyeOff className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
                  <span>Hide all</span>
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className={compactButtonClasses}
                  onClick={showAllHiddenParts}
                  disabled={!showShowAllAction}
                  title={showShowAllAction ? `Show ${hiddenPartCount} hidden parts` : "No hidden parts to show"}
                >
                  <Eye className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
                  <span>Show all</span>
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className={cn(compactButtonClasses, partLabelsVisible && "bg-[var(--ui-panel-muted)] text-[var(--ui-text)]")}
                  onClick={() => setPartLabelsVisible?.((current) => !current)}
                  aria-pressed={!!partLabelsVisible}
                  title={partLabelsVisible ? "Hide part names in the 3D view" : "Show part names in the 3D view"}
                >
                  <Eye className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
                  <span>Names</span>
                </Button>
              </div>
            </div>

            <div
              className="space-y-0.5 px-1.5 pb-2"
              role="listbox"
              aria-multiselectable="true"
              onClick={(event) => {
                if (event.target === event.currentTarget) {
                  clearAssemblySelection();
                }
              }}
            >
              {viewerLoading && !partCount ? (
                <p className="px-1.5 py-2 text-xs text-[var(--ui-text-muted)]">
                  Loading assembly parts...
                </p>
              ) : null}

              {visibleAssemblyParts.map((part) => {
                const selected = selectedPartIds.includes(part.id);
                const hovered = hoveredPartId === part.id;
                const leafPartIds = Array.isArray(part.leafPartIds) && part.leafPartIds.length ? part.leafPartIds : [part.id];
                const hidden = leafPartIds.every((id) => hiddenPartIds.includes(id));
                const inspecting = inspectedAssemblyPart?.id === part.id;
                const VisibilityIcon = hidden ? EyeOff : Eye;
                const partLabel = part.name || part.displayName || part.id;
                const visibilityLabel = hidden ? "Show" : "Hide";
                return (
                  <div
                    key={part.id}
                    ref={(node) => {
                      if (node) {
                        partRowRefs.current.set(part.id, node);
                        return;
                      }
                      partRowRefs.current.delete(part.id);
                    }}
                    className={cn(
                      "rounded-md",
                      selected || inspecting
                        ? "bg-[var(--ui-panel-muted)] shadow-[inset_2px_0_0_var(--ui-accent)]"
                        : hovered
                          ? "bg-[var(--ui-panel-muted)]"
                          : "bg-transparent",
                      hidden && "opacity-45"
                    )}
                  >
                    <div className="flex items-center gap-1">
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="h-auto min-h-8 min-w-0 flex-1 touch-manipulation justify-start rounded-md px-2 py-1.5 text-left font-normal shadow-none"
                        aria-selected={selected}
                        title={`${partLabel} (double-click to inspect)`}
                        onClick={(event) => {
                          if (event.detail > 1 || String(inspectedAssemblyPart?.nodeType || "") === "part") {
                            return;
                          }
                          togglePartSelection(part.id, { multiSelect: event.shiftKey });
                        }}
                        onDoubleClick={() => handleInspectAssemblyPart(part.id)}
                        onMouseEnter={() => setHoveredListPartId(part.id)}
                        onMouseLeave={() => {
                          setHoveredListPartId((current) => (current === part.id ? "" : current));
                        }}
                      >
                        <span className="block truncate text-[12px] font-medium leading-5 text-[var(--ui-text)]">
                          {partLabel}
                        </span>
                      </Button>

                      <div className="flex shrink-0 items-center gap-1 pr-1.5">
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          className={cn(compactIconButtonClasses, inspecting && "bg-[var(--ui-panel-muted)] text-[var(--ui-text)]")}
                          onClick={() => handleInspectAssemblyPart(part.id)}
                          aria-label={`Inspect ${partLabel}`}
                          title={`Inspect ${partLabel}`}
                          aria-pressed={inspecting}
                        >
                          <Expand className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="icon-sm"
                          className={cn(compactIconButtonClasses, hidden && "bg-[var(--ui-panel-muted)] text-[var(--ui-text)]")}
                          onClick={() => togglePartVisibility(part.id)}
                          aria-label={visibilityLabel}
                          title={visibilityLabel}
                        >
                          <VisibilityIcon className="h-3 w-3" strokeWidth={2} aria-hidden="true" />
                        </Button>
                      </div>
                    </div>
                  </div>
                );
              })}

              {!visibleAssemblyParts.length && !viewerLoading ? (
                <p className="px-1.5 py-2 text-xs text-[var(--ui-text-muted)]">
                  {normalizedPartQuery ? "No assembly parts match this filter." : "No assembly parts are available."}
                </p>
              ) : null}
            </div>
          </AccordionContent>
        </AccordionItem>
      </Accordion>
    </FileSheet>
  );
}
