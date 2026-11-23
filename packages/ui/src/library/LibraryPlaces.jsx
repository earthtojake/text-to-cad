import { ChevronDown, Plus } from "lucide-react";

import { Button } from "../primitives/button.jsx";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem, DropdownMenuSeparator, DropdownMenuTrigger } from "../primitives/dropdown-menu.jsx";
import { ScrollArea } from "../primitives/scroll-area.jsx";
import { TooltipHint } from "../primitives/tooltip.jsx";
import { treeKey } from "../primitives/tree-keys.js";
import { TREE_GLYPH_STROKE, TREE_ROW_DENSE_ICON_CLASS, TREE_ROW_NAME_CLASS, TreeRowDetail, TreeRowGlyph, TreeRowHeading, TreeRowLabel, TreeRowSurface, TreeRowsLoading } from "../primitives/tree-row.jsx";
import { PANEL_ROW_VARIABLES } from "../file-viewer/panelToggles.js";
import { useI18n } from "../i18n/index.js";
import { cn } from "../lib/utils.js";

// The home's places (`ModelLibrary.tsx`), drawn twice from one list: the sidebar a wide home has at its left, and the
// menu a narrow one has on its heading. Both are the design system's own parts: the panel's rows on the panel's
// surface (`primitives/tree-row.jsx`), and the one dropdown (`primitives/dropdown-menu.jsx`).

/**
 * @typedef {{ view: "recents" | "pinned" | "standalone" } | { view: "project", project: string }} Place
 * @typedef {object} PlaceRow  One place as its row and its menu item draw it.
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
 */

/** A press the browser should have: ⌘, Ctrl, Shift or Alt held, or another button, on a link opens it the browser's way. */
export const plainClick = event => event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;

/**
 * The sidebar: Recents and Pinned, "Projects" with its "+" over one row a project, then Standalone, on the panel's
 * surface (`data-panel-surface`: the panel's one type size, its 16px inset, its rows hanging 8px past it), 232px wide
 * at the home's full height, scrolling in the chrome's scroll region. A row is the panel's row: its glyph, its name
 * (the first to give way, whole in a hint) and its count on the right line. The place on screen is marked as an open
 * tab is (the accent fill, medium weight) and said (`aria-current`). A row is a link where the host gives the place an
 * address (`hrefOf`): a plain click shows it here, and the browser's own ways open it in a new tab. Up and Down move
 * between the rows, Home and End to the first and the last (`primitives/tree-keys.js`).
 *
 * @param {PlacesProps & { hrefOf?: ((place: Place) => string | null) | null }} props
 */
export function PlacesSidebar({ lead, projects, standalone, current, onVisit, onAddProject = null, loading = false, note = null, hrefOf = null }) {
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
  return <nav className="cad-library-sidebar" aria-label={t("home.placesAria")} data-panel-surface="home" style={PANEL_ROW_VARIABLES} onKeyDown={walk}>
    <ScrollArea className="min-h-0 flex-1">
      <div className="cad-library-places">
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
      </div>
    </ScrollArea>
  </nav>;
}

/**
 * The same places where there is no sidebar: a menu button that names the place on screen, its menu the places with
 * the same glyphs and counts, the one on screen ticked, "Projects" a muted label over the projects, and last, where
 * the host has a chooser, the "+"'s words. Its items are items, not links: a project's own ⋯ has Open in new tab.
 *
 * @param {PlacesProps & { name: string }} props  `name`: the place on screen, as its heading says it.
 */
export function PlacesMenu({ name, lead, projects, standalone, current, onVisit, onAddProject = null, loading = false, note = null }) {
  const { t } = useI18n();
  const item = entry => <DropdownMenuRadioItem key={entry.key} value={entry.key} data-place={entry.key} className={entry.missing ? "text-muted-foreground" : undefined}>
    <entry.Icon aria-hidden="true" /><span className="min-w-0 flex-1 truncate">{entry.label}</span>
    {entry.count ? <span className="cad-library-place-count">{entry.count}</span> : null}
  </DropdownMenuRadioItem>;
  const every = [...lead, ...projects, standalone];
  return <DropdownMenu modal={false}>
    <DropdownMenuTrigger asChild>
      <Button variant="ghost" size="xs" className="cad-library-place-button h-control min-w-0 gap-1 px-2 text-ui" aria-label={`${t("home.placesAria")}: ${name}`}>
        <span className="cad-library-label">{name}</span><ChevronDown className="size-3.5 text-muted-foreground" aria-hidden="true" /></Button>
    </DropdownMenuTrigger>
    <DropdownMenuContent align="start" className="min-w-56">
      <DropdownMenuRadioGroup value={current} onValueChange={key => { const chosen = every.find(entry => entry.key === key); if (chosen) onVisit(chosen.place); }}>
        {lead.map(item)}
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-muted-foreground">{t("home.projects")}</DropdownMenuLabel>
        {loading || note ? <DropdownMenuLabel className="text-muted-foreground" data-places-note="">{loading ? t("home.loadingProjects") : note}</DropdownMenuLabel>
          : projects.map(item)}
        <DropdownMenuSeparator />
        {item(standalone)}
      </DropdownMenuRadioGroup>
      {onAddProject ? <>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={onAddProject}><Plus aria-hidden="true" />{t("home.addProject")}</DropdownMenuItem>
      </> : null}
    </DropdownMenuContent>
  </DropdownMenu>;
}
