import {
  Blend,
  Bot,
  Box,
  Code,
  DraftingCompass,
  FileBox,
  LoaderCircle,
  Printer,
  Triangle
} from "lucide-react";

import { cn } from "@/ui/utils";
import {
  ENTRY_ICON_KIND,
  entryIconKind,
  isCodeDerivedEntry
} from "@/workbench/entryIconKind";

// One icon table for every surface that lists files — the sidebar, the
// breadcrumb menu, and the home list — so a file cannot read as one thing in
// one place and something else in another.
const ENTRY_ICON_COMPONENTS = {
  [ENTRY_ICON_KIND.LOADING]: LoaderCircle,
  // A solid cube for the solid-model format; STL gets the triangle it is
  // actually made of, so mesh and B-rep never read alike.
  [ENTRY_ICON_KIND.STEP]: Box,
  [ENTRY_ICON_KIND.STL_MESH]: Triangle,
  // 3MF is the 3D-print package.
  [ENTRY_ICON_KIND.THREE_MF_MESH]: Printer,
  [ENTRY_ICON_KIND.GLB_MESH]: FileBox,
  [ENTRY_ICON_KIND.DXF]: DraftingCompass,
  [ENTRY_ICON_KIND.ROBOT]: Bot,
  // Two overlapping shapes: the smooth boolean that defines an SDF model.
  [ENTRY_ICON_KIND.IMPLICIT]: Blend
};

export function entryIconComponent(entry, sourceFormat, status) {
  return ENTRY_ICON_COMPONENTS[entryIconKind(entry, { sourceFormat, status })] || Box;
}

// A file's icon says what it IS; the badge says where it came from. A generated
// model therefore carries the icon of the imported file it stands in for, with a
// small code mark in the corner.
export default function EntryIcon({
  entry,
  sourceFormat = "",
  status = {},
  className,
  badgeClassName,
  spinning = false
}) {
  const Icon = entryIconComponent(entry, sourceFormat, status);
  const codeDerived = isCodeDerivedEntry(entry);

  const glyph = (
    <Icon className={cn(className, spinning && "animate-spin")} aria-hidden="true" />
  );
  if (!codeDerived) {
    return glyph;
  }

  return (
    <span className="relative inline-flex shrink-0 items-center justify-center" aria-hidden="true">
      {glyph}
      <span
        className={cn(
          "absolute -bottom-1 -right-1 flex size-2.5 items-center justify-center rounded-[3px]",
          "border border-sidebar bg-sidebar text-sidebar-foreground shadow-sm",
          badgeClassName
        )}
      >
        <Code className="size-2" strokeWidth={2.5} />
      </span>
    </span>
  );
}
