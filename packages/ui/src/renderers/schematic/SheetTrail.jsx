import { useI18n } from "@cad/ui/i18n";
import { Fragment } from "react";
import { ChevronRight } from "lucide-react";
import { cn } from "@cad/ui/utils";
import { FLOATING_SURFACE_CLASS } from "../../lib/floatingSurface.js";

/**
 * The way back up from a sheet entered: the sheets from the root down to the one shown, under the strip,
 * as a breadcrumb — each sheet above a button that shows it, the one shown its name alone. It is there
 * only below the root; the Hierarchy tab is the whole tree.
 *
 * @param {{ index: object, trail: readonly string[], onShow(path: string): void }} props
 */
export default function SheetTrail({ index, trail, onShow }) {
  const { t } = useI18n();
  return <nav aria-label={t("schematic.text.sheet_trail")} data-schematic-trail=""
    className={cn(FLOATING_SURFACE_CLASS, "pointer-events-auto flex max-w-full min-w-0 items-center gap-0.5 rounded-md px-1 py-0.5 text-tiny")}>
    {trail.map((path, at) => {
      const last = at === trail.length - 1;
      return <Fragment key={path}>
        {at ? <ChevronRight className="size-3 shrink-0 text-muted-foreground" aria-hidden="true" /> : null}
        {last ? <span className="truncate px-1.5 py-0.5 font-medium" aria-current="page">{index.sheetName(path)}</span>
          : <button type="button" className="truncate rounded px-1.5 py-0.5 text-muted-foreground hover:bg-accent hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => onShow(path)} data-schematic-trail-sheet={path}>{index.sheetName(path)}</button>}
      </Fragment>;
    })}
  </nav>;
}
