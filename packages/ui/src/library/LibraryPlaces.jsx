import { Plus } from "lucide-react";

import { Button } from "../primitives/button.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { treeKey } from "../primitives/tree-keys.js";
import { TREE_GLYPH_STROKE, TREE_ROW_DENSE_ICON_CLASS, TREE_ROW_NAME_CLASS, TreeRowGlyph, TreeRowHeading, TreeRowLabel, TreeRowSurface, TreeRowsLoading } from "../primitives/tree-row.jsx";
import { useI18n } from "../i18n/index.js";
import { cn } from "../lib/utils.js";

// The home's places (`ModelLibrary.tsx`), the list its sidebar holds (`LibrarySidebar.jsx`: pinned, peeking, or a
// phone's sheet), in the design system's own parts: the panel's rows on the panel's surface (`primitives/tree-row.jsx`).

/**
 * @typedef {{ view: "recents" | "pinned" } | { view: "project", project: string, path?: string }} Place
 * @typedef {object} PlaceRow  One place as its row draws it: its glyph and its name, and no count, as Figma's and
 *   Drive's sidebars have none.
 * @property {Place} place
 * @property {string} key  The place as one word (`placeKey`): what marks the row of the place on screen.
 * @property {string} label
 * @property {import("react").ComponentType<any>} Icon
 * @property {boolean} [missing]  A project whose folder is gone: drawn muted.
 * @typedef {object} PlacesProps
 * @property {readonly PlaceRow[]} lead  Recents and Starred.
 * @property {readonly PlaceRow[]} projects  One a project, the latest activity first: its glyph and its name.
 * @property {string} current  The key of the place on screen.
 * @property {(place: Place) => void} onVisit
 * @property {(() => void) | null} [onAddProject]  Import's Folder, where the host has a chooser: the "+" by Projects.
 * @property {boolean} [loading]  The projects are being read for the first time.
 * @property {string | null} [note]  What stands where the projects would be: none yet, or they could not be read.
 * @property {((place: Place) => string | null) | null} [hrefOf]  A place's own address, where the host gives it one.
 * @property {boolean} [footed]  The panel's foot stands under the list, and keeps clear of a host's composer itself.
 */

/**
 * The list's own box, the panel's body: on the panel's inset, 8px under the navbar and 8px over what follows it (the
 * panel's foot; with none, clear of a host's composer floating over the bottom), its groups 16px apart.
 * @param {boolean} footed
 */
export const placesClass = footed => cn("flex flex-col gap-4 px-(--panel-inset) pt-2", footed ? "pb-2" : "pb-[calc(var(--cad-host-bottom-inset,0px)+8px)]");

const LIST_CLASS = "m-0 list-none p-0";

/** A press the browser should have: ⌘, Ctrl, Shift or Alt held, or another button, on a link opens it the browser's way. */
export const plainClick = event => event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;

/**
 * A way to a place, as a row of the list primitive (`primitives/tree-row.jsx`): its glyph in the row's slot, then its
 * name (the first to give way, whole in a hint). A link where the place has an address (`href`): a plain click is
 * `onPress`, in this view, and the browser's own ways open it in a new tab; a button otherwise. `active`: the place on
 * screen, marked as an open tab is (the accent fill, medium weight) and said (`aria-current`). The sidebar's places are
 * these.
 *
 * @param {{ href?: string | null, label: string, Icon: import("react").ComponentType<any>, active?: boolean, missing?: boolean,
 *   onPress(): void, className?: string } & Record<string, unknown>} props
 */
export function PlaceLink({ href = null, label, Icon, active = false, missing = false, onPress, className, ...props }) {
  return <TooltipHint content={label} overflowOnly side="right">
    <TreeRowSurface as={href ? "a" : "button"} href={href ?? undefined} type={href ? undefined : "button"} dense depth={0}
      data-missing={missing || undefined} aria-current={active ? "page" : undefined}
      className={cn("no-underline outline-none focus-visible:ring-2 focus-visible:ring-ring/45", active && "bg-accent font-medium hover:bg-accent",
        missing && "text-muted-foreground", className)}
      onClick={event => { if (href && !plainClick(event)) return; event.preventDefault(); onPress(); }} {...props}>
      <TreeRowGlyph><Icon className={TREE_ROW_DENSE_ICON_CLASS} strokeWidth={TREE_GLYPH_STROKE} aria-hidden="true" /></TreeRowGlyph>
      <span className={cn(TREE_ROW_NAME_CLASS, "pointer-events-none")}>
        <TreeRowLabel className="flex-1">{label}</TreeRowLabel>
      </span>
    </TreeRowSurface>
  </TooltipHint>;
}

/**
 * The places: Recents and Starred, then "Projects" with its "+" over one row a project, on the panel's 16px inset (the
 * surface's: its rows hanging 8px past the inset). A row is the panel's row: its glyph and its name (the first to give
 * way, whole in a hint), with no count. The place on screen is marked as an open tab is (the accent fill, medium
 * weight) and said (`aria-current`). A row is a link where the host gives the place an address (`hrefOf`): a plain
 * click shows it here, and the browser's own ways open it in a new tab. Up and Down move between the rows, Home and
 * End to the first and the last (`primitives/tree-keys.js`).
 *
 * @param {PlacesProps} props
 */
export function PlacesList({ lead, projects, current, onVisit, onAddProject = null, loading = false, note = null, hrefOf = null, footed = false }) {
  const { t } = useI18n();
  const walk = event => {
    const rows = [...event.currentTarget.querySelectorAll("[data-place]")];
    const move = treeKey(event.key, rows.map(() => ({ depth: 0, branch: false, open: false })), rows.indexOf(event.target.closest?.("[data-place]")));
    if (!move || !("focus" in move)) return;
    event.preventDefault();
    rows[move.focus]?.focus();
  };
  const row = entry => <li key={entry.key} className="min-w-0">
    <PlaceLink href={hrefOf?.(entry.place) ?? null} label={entry.label} Icon={entry.Icon} active={entry.key === current} missing={entry.missing}
      onPress={() => onVisit(entry.place)} data-place={entry.key} />
  </li>;
  return <nav className={placesClass(footed)} aria-label={t("home.placesAria")} onKeyDown={walk} data-library-places="">
    <ul className={LIST_CLASS}>{lead.map(row)}</ul>
    <div>
      {/* The "+" by Projects: a small icon button, hanging 6px (its own padding) past the inset so its glyph ends on it. */}
      <div className="flex min-w-0 items-center">
        <TreeRowHeading as="h2" className="flex-1">{t("home.projects")}</TreeRowHeading>
        {onAddProject ? <Button variant="ghost" size="icon-xs" className="-mr-1.5 flex-none text-muted-foreground" aria-label={t("home.addProject")} onClick={onAddProject}>
          <Plus aria-hidden="true" /></Button> : null}
      </div>
      {loading ? <TreeRowsLoading label={t("home.loadingProjects")} rows={3} />
        : note ? <TreeRowHeading as="p" className="m-0" data-library-places-note="">{note}</TreeRowHeading>
          : <ul className={LIST_CLASS} aria-label={t("home.projects")}>{projects.map(row)}</ul>}
    </div>
  </nav>;
}
