import { Fragment, useEffect, useMemo, useRef, useState } from "react";
import { Box, Boxes, ChevronRight } from "lucide-react";
import { cn } from "@/ui/utils";
import RobotComponentReference from "./RobotComponentReference";
import { TREE_GLYPH_ICON_CLASSES, TreeDepthGuides, treeRowClassName, treeRowIndentPx } from "./treeRow";

// A robot's components ARE a hierarchy — a link owns the named objects inside the
// meshes it links — so they are drawn as one: link rows that expand, objects beneath
// them, the same indentation, guides and row states the STEP tree uses. A flat list
// of every object in the robot is unreadable at the sizes real robots reach (tom.urdf
// is 78 objects across 8 links, 51 of them under one link).
//
// Links start COLLAPSED. The first thing the panel should answer is "which links does
// this robot have", and expanding is one click; opening on 78 rows answers nothing.

function ComponentRow({ component, selected, onSelect, onHover }) {
  const rowRef = useRef(null);
  useEffect(() => {
    if (selected) rowRef.current?.scrollIntoView({ block: "nearest" });
  }, [selected]);
  return (
    <div className="relative min-w-0">
      <TreeDepthGuides depth={1} />
      <div style={{ marginLeft: `${treeRowIndentPx(1)}px` }}>
        <button
          ref={rowRef}
          type="button"
          role="treeitem"
          aria-level={2}
          aria-selected={selected}
          title={component.name}
          className={treeRowClassName({ selected })}
          onClick={(event) => onSelect(component.id, { multiSelect: event.ctrlKey || event.metaKey || event.shiftKey })}
          onMouseEnter={() => onHover(component.id)}
          onMouseLeave={() => onHover("")}
          onFocus={() => onHover(component.id)}
          onBlur={() => onHover("")}
        >
          <Box className={TREE_GLYPH_ICON_CLASSES} strokeWidth={1.6} aria-hidden="true" />
          <span className="truncate">{component.name}</span>
        </button>
      </div>
    </div>
  );
}

function LinkRow({ linkName, count, expanded, selectedCount, onToggle }) {
  return (
    <button
      type="button"
      role="treeitem"
      aria-level={1}
      aria-expanded={expanded}
      title={`${linkName} — ${count} component${count === 1 ? "" : "s"}`}
      className={treeRowClassName({ hovered: false })}
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

export default function RobotComponentsSection({ components, selectedIds, onSelect, onHover }) {
  const groups = useMemo(() => groupByLink(components), [components]);
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
                count={entries.length}
                expanded={expanded}
                selectedCount={entries.filter((component) => selectedIds.includes(component.id)).length}
                onToggle={() => toggleLink(linkName)}
              />
              {expanded ? entries.map((component) => (
                <ComponentRow
                  key={component.id}
                  component={component}
                  selected={selectedIds.includes(component.id)}
                  onSelect={onSelect}
                  onHover={onHover}
                />
              )) : null}
            </Fragment>
          );
        })}
      </div>
      <RobotComponentReference components={components} selectedIds={selectedIds} />
    </div>
  );
}
