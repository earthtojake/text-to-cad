import { cn } from "@cad/ui/utils";

// A key, as the chrome writes one beside what it does (`docs/design-system.md`, "Tooltips"): the search's keys' line and
// its field's key, the Home's way back. A muted `text-tiny` hint at regular weight in a hairline box on the page's
// colour, its line and its two edges tall (the chip less 2), 4px in, a tile's corners. A menu's key hint is the menu's
// own (`DropdownMenuShortcut`), with no box.

/** @param {import("react").ComponentPropsWithoutRef<"kbd">} props */
export function Kbd({ className, ...props }) {
  return <kbd data-slot="kbd" className={cn("inline-flex h-[calc(var(--cad-chip)-2px)] shrink-0 items-center rounded-control border border-border bg-background px-1 "
    + "font-sans text-tiny font-normal text-muted-foreground", className)} {...props} />;
}
