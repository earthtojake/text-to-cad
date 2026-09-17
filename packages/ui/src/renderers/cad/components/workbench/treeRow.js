// The LOOK of a tree row: indentation, depth guides, glyph size, row states.
//
// Shared by the STEP tree and the robot Components tree so the two read as one
// control rather than two that resemble each other. What is NOT here is the STEP
// tree's machinery — virtualization, context menus, isolation, hide/show, keyboard
// roving — because that is the part a second tree must not clone to look alike.
import { cn } from "@hardcore/ui/utils";

export const TREE_INDENT_PX = 26;
export const TREE_GUIDE_OFFSET_PX = 14;
// Past this depth rows stop indenting: a deep branch keeps its name readable in a
// narrow sidebar, and the guides already say how deep it is.
export const TREE_MAX_INDENT_PX = 156;

export const TREE_GLYPH_ICON_CLASSES = "size-3.5 shrink-0 text-current/60";

export function treeRowIndentPx(depth) {
  return Math.min(Math.max(Math.trunc(Number(depth) || 0), 0) * TREE_INDENT_PX, TREE_MAX_INDENT_PX);
}

// One vertical rule per ancestor level, so a child reads as belonging to the row
// above it rather than as a row that happens to start further right.
export function TreeDepthGuides({ depth }) {
  const normalizedDepth = Math.min(
    Math.max(Math.trunc(Number(depth) || 0), 0),
    Math.floor(TREE_MAX_INDENT_PX / TREE_INDENT_PX)
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
          style={{ left: `${index * TREE_INDENT_PX + TREE_GUIDE_OFFSET_PX}px` }}
        />
      ))}
    </span>
  );
}

export function treeRowClassName({ selected = false, hovered = false, muted = false } = {}) {
  return cn(
    "flex h-7 min-w-0 w-full max-w-full items-center gap-2 rounded-md px-2 text-xs font-normal outline-none transition-colors",
    "cursor-pointer text-sidebar-foreground hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
    "focus-visible:bg-sidebar-accent focus-visible:text-sidebar-accent-foreground",
    selected
      ? "bg-sidebar-accent font-medium text-sidebar-accent-foreground"
      : hovered && "bg-sidebar-accent text-sidebar-accent-foreground",
    muted && "opacity-45"
  );
}
