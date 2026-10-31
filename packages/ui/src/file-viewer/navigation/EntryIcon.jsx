import { File, LoaderCircle } from "lucide-react";

import { cn } from "@text-to-cad/ui/utils";
import {
  ENTRY_ICON_KIND,
  entryIconKind
} from "./entryIconKind.js";

// One glyph for every CAD file, on every surface that lists files — the
// explorer, the Home, the name menu: lucide's plain `File`, so a file reads as
// a file at a glance, and the name beside it says which kind. (A model, built
// from code, is lucide's `Box`: `DocumentGlyph`.) Only a file still loading
// differs: the spinner.
const ENTRY_ICON_COMPONENTS = {
  [ENTRY_ICON_KIND.LOADING]: LoaderCircle,
};

export function entryIconComponent(entry, sourceFormat, status) {
  return ENTRY_ICON_COMPONENTS[entryIconKind(entry, { sourceFormat, status })] || File;
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
