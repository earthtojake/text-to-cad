import { Button } from "@/components/ui/button";
import { cn } from "@/ui/utils";

import { Breadcrumbs } from "./Breadcrumbs.jsx";

/**
 * The row above a file: the breadcrumb on the left, the panel toggles on the
 * right, and nothing between them but space.
 *
 * One row, one height, one set of classes, in both apps — the desktop's file
 * tab and the standalone viewer's window are the same surface with the same
 * address bar over it, and a person moving between them should not have to
 * find it twice. What differs is what hangs off the ends, so the ends are
 * slots: the desktop puts a worktree label at the left and its panel toggles
 * at the right, the standalone puts Discord, GitHub and its version chip in
 * front of the same toggles.
 *
 * Everything else — the crumbs, their menus, the truncation rule, the
 * separators — is `Breadcrumbs.jsx` and is not a slot.
 */

/**
 * One class for every toggle at the end of the row, so "highlighted while its
 * panel is open" looks the same on all of them and the same in both apps.
 */
export const PANEL_TOGGLE_CLASSES =
  "size-6 text-muted-foreground aria-pressed:bg-accent aria-pressed:text-accent-foreground";

/**
 * One panel's toggle. `active` is the panel being open, not the button being
 * pressed: it is `aria-pressed`, which is what paints it.
 *
 * @param {object} props
 * @param {import("react").ElementType} props.icon
 * @param {string} props.label The accessible name and the tooltip — what pressing it does.
 * @param {boolean} props.active
 * @param {() => void} props.onClick
 * @param {string} [props.id] Written as `data-file-panel`, for the host's tests.
 * @param {string} [props.testId]
 */
export function PanelToggle({ icon: Icon, label, active, onClick, id, testId }) {
  return (
    <Button
      aria-label={label}
      aria-pressed={active}
      className={PANEL_TOGGLE_CLASSES}
      {...(id ? { "data-file-panel": id } : {})}
      {...(testId ? { "data-testid": testId } : {})}
      onClick={onClick}
      size="icon-xs"
      title={label}
      type="button"
      variant="ghost"
    >
      <Icon className="size-3.5" />
    </Button>
  );
}

/**
 * @param {object} props
 * @param {import("./crumbs.js").Crumb[]} props.crumbs
 * @param {import("./Breadcrumbs.jsx").CrumbSource} props.source
 * @param {string|null} props.activePath
 * @param {(path: string, entry: import("./crumbs.js").ListingEntry) => void} props.onOpen
 * @param {import("react").ReactNode} [props.leading]
 *   Drawn before the first crumb, inside the breadcrumb's own overflow box —
 *   the desktop's worktree label. It shrinks and truncates with the folders.
 * @param {import("react").ReactNode} [props.status]
 *   Drawn after the last crumb: the desktop's unsaved-changes dot, the
 *   standalone's loading spinner. Small, and about the open file.
 * @param {import("react").ReactNode} [props.trailing]
 *   The right end: panel toggles, and whatever the host puts in front of
 *   them. Never shrinks.
 * @param {string} [props.className]
 */
export function FileNavRow({
  crumbs,
  source,
  activePath,
  onOpen,
  leading = null,
  status = null,
  trailing = null,
  className
}) {
  return (
    <header
      className={cn(
        "flex h-9 shrink-0 items-center gap-2 border-b border-border bg-background px-2 text-foreground",
        className
      )}
    >
      {/*
        The file's name is the crumb that matters, so it is the one that never
        shrinks; the folders give up their width first and truncate. Every
        crumb is `min-w-0` so flex can take the width back — a `shrink-0` on
        the folders is how they came to be drawn over each other in a narrow
        pane.
      */}
      <nav
        aria-label="Breadcrumb"
        className="flex min-w-0 flex-1 items-center gap-1 overflow-hidden text-[13px]"
      >
        {leading}
        <Breadcrumbs activePath={activePath} crumbs={crumbs} onOpen={onOpen} source={source} />
        {status}
      </nav>

      {/*
        One toggle per panel, in declaration order with the files toggle last,
        and never any other order: the right end of this row is the same
        control whatever is open and whatever kind of file this is, so it is
        the one thing in the pane a person can always find in the same place.
      */}
      <div className="flex shrink-0 items-center gap-0.5">{trailing}</div>
    </header>
  );
}
