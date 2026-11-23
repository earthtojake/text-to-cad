import { Plus } from "lucide-react";

import { Button } from "../primitives/button.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { treeKey } from "../primitives/tree-keys.js";
import { TREE_GLYPH_STROKE, TREE_ROW_DENSE_ICON_CLASS, TREE_ROW_NAME_CLASS, TreeRowDetail, TreeRowGlyph, TreeRowHeading, TreeRowLabel, TreeRowSurface, TreeRowsLoading } from "../primitives/tree-row.jsx";
import { useI18n } from "../i18n/index.js";
import { cn } from "../lib/utils.js";

// The home's places (`ModelLibrary.tsx`), the list its sidebar holds (`LibrarySidebar.jsx`: pinned, peeking, or a
// phone's sheet), in the design system's own parts: the panel's rows on the panel's surface (`primitives/tree-row.jsx`).

/**
 * @typedef {{ view: "recents" | "pinned" | "standalone" } | { view: "project", project: string }} Place
 * @typedef {object} PlaceRow  One place as its row draws it.
 * @property {Place} place
 * @property {string} key  The place as one word (`placeKey`): what marks the row of the place on screen.
 * @property {string} label
 * @property {number} count  Its documents; none is not said.
 * @property {import("react").ComponentType<any>} Icon
 * @property {boolean} [missing]  A project whose folder is gone: drawn muted.
 * @typedef {object} PlacesProps
 * @property {readonly PlaceRow[]} lead  Recents and Pinned.
 * @property {readonly PlaceRow[]} projects  One a project, the latest activity first.
 * @property {PlaceRow} standalone
 * @property {string} current  The key of the place on screen.
 * @property {(place: Place) => void} onVisit
 * @property {(() => void) | null} [onAddProject]  Import's Folder, where the host has a chooser: the "+" by Projects.
 * @property {boolean} [loading]  The projects are being read for the first time.
 * @property {string | null} [note]  What stands where the projects would be: none yet, or they could not be read.
 * @property {((place: Place) => string | null) | null} [hrefOf]  A place's own address, where the host gives it one.
 */

/** A press the browser should have: ⌘, Ctrl, Shift or Alt held, or another button, on a link opens it the browser's way. */
export const plainClick = event => event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;

/**
 * The places: Recents and Pinned, "Projects" with its "+" over one row a project, then Standalone, on the panel's
 * 16px inset (the surface's: its one type size, its rows hanging 8px past the inset). A row is the panel's row: its
 * glyph, its name (the first to give way, whole in a hint) and its count on the right line. The place on screen is
 * marked as an open tab is (the accent fill, medium weight) and said (`aria-current`). A row is a link where the host
 * gives the place an address (`hrefOf`): a plain click shows it here, and the browser's own ways open it in a new tab.
 * Up and Down move between the rows, Home and End to the first and the last (`primitives/tree-keys.js`).
 *
 * @param {PlacesProps} props
 */
export function PlacesList({ lead, projects, standalone, current, onVisit, onAddProject = null, loading = false, note = null, hrefOf = null }) {
  const { t } = useI18n();
  const walk = event => {
    const rows = [...event.currentTarget.querySelectorAll("[data-place]")];
    const move = treeKey(event.key, rows.map(() => ({ depth: 0, branch: false, open: false })), rows.indexOf(event.target.closest?.("[data-place]")));
    if (!move || !("focus" in move)) return;
    event.preventDefault();
    rows[move.focus]?.focus();
  };
  const row = entry => {
    const active = entry.key === current;
    const href = hrefOf?.(entry.place) ?? null;
    return <li key={entry.key} className="min-w-0">
      <TooltipHint content={entry.label} overflowOnly side="right">
        <TreeRowSurface as={href ? "a" : "button"} href={href ?? undefined} type={href ? undefined : "button"} dense depth={0}
          data-place={entry.key} data-missing={entry.missing || undefined} aria-current={active ? "page" : undefined}
          className={cn("no-underline outline-none focus-visible:ring-2 focus-visible:ring-ring/45", active && "bg-accent font-medium hover:bg-accent",
            entry.missing && "text-muted-foreground")}
          onClick={event => { if (href && !plainClick(event)) return; event.preventDefault(); onVisit(entry.place); }}>
          <TreeRowGlyph><entry.Icon className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} aria-hidden="true" /></TreeRowGlyph>
          <span className={cn(TREE_ROW_NAME_CLASS, "pointer-events-none")}>
            <TreeRowLabel className="flex-1">{entry.label}</TreeRowLabel>
            {entry.count ? <TreeRowDetail className="flex-none tabular-nums">{entry.count}</TreeRowDetail> : null}
          </span>
        </TreeRowSurface>
      </TooltipHint>
    </li>;
  };
  return <nav className="cad-library-places" aria-label={t("home.placesAria")} onKeyDown={walk}>
    <ul>{lead.map(row)}</ul>
    <div>
      <div className="cad-library-places-head">
        <TreeRowHeading as="h2" className="flex-1">{t("home.projects")}</TreeRowHeading>
        {onAddProject ? <Button variant="ghost" size="icon-xs" className="cad-library-places-add" aria-label={t("home.addProject")} onClick={onAddProject}>
          <Plus aria-hidden="true" /></Button> : null}
      </div>
      {loading ? <TreeRowsLoading label={t("home.loadingProjects")} rows={3} />
        : note ? <p className="cad-library-places-note">{note}</p>
          : <ul aria-label={t("home.projects")}>{projects.map(row)}</ul>}
    </div>
    <ul>{row(standalone)}</ul>
  </nav>;
}
