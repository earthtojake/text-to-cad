import {
  Bot,
  Box,
  DraftingCompass,
  FileBox,
  LoaderCircle,
  Printer,
  Triangle
} from "lucide-react";

import { cn } from "@/ui/utils";
import {
  ENTRY_ICON_KIND,
  entryIconKind
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
  [ENTRY_ICON_KIND.ROBOT]: Bot
};

export function entryIconComponent(entry, sourceFormat, status) {
  return ENTRY_ICON_COMPONENTS[entryIconKind(entry, { sourceFormat, status })] || Box;
}

// A file's icon says what it IS — nothing more. How the file came to exist (a
// model script ran, or someone dropped a foreign document in the directory) is
// not a property of the file the viewer shows, so no badge encodes it.
export default function EntryIcon({
  entry,
  sourceFormat = "",
  status = {},
  className,
  spinning = false,
  // Only the shared chrome sets this, so a CAD glyph in a file list is drawn
  // at the same weight as the lucide icons beside it (`shell/icons.jsx`).
  strokeWidth
}) {
  const Icon = entryIconComponent(entry, sourceFormat, status);
  return (
    <Icon
      className={cn(className, spinning && "animate-spin")}
      strokeWidth={strokeWidth}
      aria-hidden="true"
    />
  );
}
