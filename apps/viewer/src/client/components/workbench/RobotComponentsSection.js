import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Box, Boxes, ChevronRight, Eye, EyeOff } from "lucide-react";
import { cn } from "@/ui/utils";
import { Button } from "../ui/button";
import RobotComponentDetails from "./RobotComponentDetails";
import { TREE_GLYPH_ICON_CLASSES, TreeDepthGuides, treeRowClassName, treeRowIndentPx } from "./treeRow";

// A robot's components ARE a hierarchy — a link owns the named objects inside the
// meshes it links — so they are drawn as one: link rows that expand, objects beneath
// them, the same indentation, guides and row states the STEP tree uses. A flat list
// of every object in the robot is unreadable at the sizes real robots reach (tom.urdf
// is 78 objects across 8 links, 51 of them under one link).
//
// Links start COLLAPSED. The first thing the panel should answer is "which links does
// this robot have", and expanding is one click; opening on 78 rows answers nothing.

const treeActionButtonClasses = "h-5 w-5 rounded-sm px-0 text-current/60 shadow-none hover:bg-sidebar-accent/45 hover:text-sidebar-accent-foreground focus-visible:bg-sidebar-accent/45";

// Hide/show, from the text-to-cad-fourbar viewer's robot tree: one button per row, for
// a component or for every component in a link.
function visibilityState(componentIds, hiddenIds) {
  const ids = Array.isArray(componentIds) ? componentIds.filter(Boolean) : [];
  const hiddenCount = ids.filter((id) => hiddenIds.has(id)).length;
  return Object.freeze({
    ids: Object.freeze(ids),
    allHidden: ids.length > 0 && hiddenCount === ids.length,
    someHidden: hiddenCount > 0 && hiddenCount < ids.length
  });
}

function VisibilityButton({ state, label, onVisibilityChange }) {
  const action = state.allHidden ? "Show" : "Hide";
  return (
    <Button
      type="button"
      variant="ghost"
      size="icon-sm"
      className={cn(treeActionButtonClasses, "shrink-0", state.someHidden && "opacity-70")}
      disabled={!state.ids.length || typeof onVisibilityChange !== "function"}
      aria-label={`${action} ${label}`}
      title={state.someHidden ? `Hide all geometry in ${label}` : `${action} ${label}`}
      onClick={(event) => {
        event.stopPropagation();
        onVisibilityChange?.(state.ids, state.allHidden);
      }}
    >
      {state.allHidden ? (
        <Eye className="size-3.5" strokeWidth={1.8} aria-hidden="true" />
      ) : (
        <EyeOff className="size-3.5" strokeWidth={1.8} aria-hidden="true" />
      )}
    </Button>
  );
}

function hiddenRowClasses(state) {
  return cn(state.allHidden && "opacity-50", state.someHidden && "opacity-75");
}

function ComponentRow({ component, selected, hiddenIds, onSelect, onHover, onVisibilityChange }) {
  const rowRef = useRef(null);
  useEffect(() => {
    if (selected) rowRef.current?.scrollIntoView({ block: "nearest" });
  }, [selected]);
  const hiddenState = visibilityState([component.id], hiddenIds);
  return (
    <div className="relative min-w-0">
      <TreeDepthGuides depth={1} />
      <div
        className={cn(treeRowClassName({ selected }), "gap-1 pr-1", hiddenRowClasses(hiddenState))}
        style={{ marginLeft: `${treeRowIndentPx(1)}px`, width: `calc(100% - ${treeRowIndentPx(1)}px)` }}
      >
        <button
          ref={rowRef}
          type="button"
          role="treeitem"
          aria-level={2}
          aria-selected={selected}
          title={component.name}
          className="flex h-full min-w-0 flex-1 items-center gap-2 text-left outline-none"
          onClick={(event) => onSelect(component.id, { multiSelect: event.ctrlKey || event.metaKey || event.shiftKey })}
          onMouseEnter={() => onHover(component.id)}
          onMouseLeave={() => onHover("")}
          onFocus={() => onHover(component.id)}
          onBlur={() => onHover("")}
        >
          <Box className={TREE_GLYPH_ICON_CLASSES} strokeWidth={1.6} aria-hidden="true" />
          <span className="truncate">{component.name}</span>
        </button>
        <VisibilityButton state={hiddenState} label={component.name} onVisibilityChange={onVisibilityChange} />
      </div>
    </div>
  );
}

function LinkRow({ linkName, componentIds, expanded, selectedCount, hiddenIds, onToggle, onVisibilityChange }) {
  const count = componentIds.length;
  const hiddenState = visibilityState(componentIds, hiddenIds);
  return (
    <div className={cn(treeRowClassName({ hovered: false }), "gap-1 pr-1", hiddenRowClasses(hiddenState))}>
      <button
        type="button"
        role="treeitem"
        aria-level={1}
        aria-expanded={expanded}
        title={`${linkName} — ${count} component${count === 1 ? "" : "s"}`}
        className="flex h-full min-w-0 flex-1 items-center gap-2 text-left outline-none"
        onClick={onToggle}
      >
        <ChevronRight
          className={cn(TREE_GLYPH_ICON_CLASSES, "transition-transform", expanded && "rotate-90")}
          strokeWidth={1.6}
          aria-hidden="true"
        />
        <Boxes className={TREE_GLYPH_ICON_CLASSES} strokeWidth={1.6} aria-hidden="true" />
        <span className="truncate font-medium">{linkName}</span>
        <span className="ml-auto shrink-0 pl-2 tabular-nums text-[11px] text-sidebar-foreground/55">
          {selectedCount ? `${selectedCount}/${count}` : count}
        </span>
      </button>
      <VisibilityButton state={hiddenState} label={linkName} onVisibilityChange={onVisibilityChange} />
    </div>
  );
}

// A plain loop over one Map, not `Object.groupBy`: that is newer than the browsers this
// client targets, and one pass building one Map is what the grouping actually needs.
// Insertion order is the components' render order, so links appear as the robot lists them.
function groupByLink(components) {
  const groups = new Map();
  for (const component of components) {
    const existing = groups.get(component.linkName);
    if (existing) {
      existing.push(component);
    } else {
      groups.set(component.linkName, [component]);
    }
  }
  return groups;
}

export default function RobotComponentsSection({
  components,
  selectedIds,
  onSelect,
  onHover,
  hiddenComponentIds = [],
  onVisibilityChange
}) {
  const groups = useMemo(() => groupByLink(components), [components]);
  const hiddenIds = useMemo(() => new Set(hiddenComponentIds), [hiddenComponentIds]);
  const [expandedLinks, setExpandedLinks] = useState(() => new Set());

  // A selection made in the VIEWPORT has no row to land on while its link is collapsed,
  // and a panel that says nothing about what the user just clicked is the bug this avoids.
  const selectedLinks = useMemo(() => {
    const links = new Set();
    for (const component of components) {
      if (selectedIds.includes(component.id)) links.add(component.linkName);
    }
    return links;
  }, [components, selectedIds]);
  useEffect(() => {
    if (!selectedLinks.size) return;
    setExpandedLinks((current) => {
      if ([...selectedLinks].every((linkName) => current.has(linkName))) return current;
      return new Set([...current, ...selectedLinks]);
    });
  }, [selectedLinks]);

  const toggleLink = (linkName) => setExpandedLinks((current) => {
    const next = new Set(current);
    if (!next.delete(linkName)) next.add(linkName);
    return next;
  });

  return (
    <div className="flex min-w-0 flex-col gap-3">
      <div role="tree" aria-label="Robot components" className="min-w-0">
        {[...groups].map(([linkName, entries]) => {
          const expanded = expandedLinks.has(linkName);
          return (
            <Fragment key={linkName}>
              <LinkRow
                linkName={linkName}
                componentIds={entries.map((component) => component.id)}
                expanded={expanded}
                selectedCount={entries.filter((component) => selectedIds.includes(component.id)).length}
                hiddenIds={hiddenIds}
                onToggle={() => toggleLink(linkName)}
                onVisibilityChange={onVisibilityChange}
              />
              {expanded ? entries.map((component) => (
                <ComponentRow
                  key={component.id}
                  component={component}
                  selected={selectedIds.includes(component.id)}
                  hiddenIds={hiddenIds}
                  onSelect={onSelect}
                  onHover={onHover}
                  onVisibilityChange={onVisibilityChange}
                />
              )) : null}
            </Fragment>
          );
        })}
      </div>
      <RobotComponentDetails components={components} selectedIds={selectedIds} />
    </div>
  );
}
