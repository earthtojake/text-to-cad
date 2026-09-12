/**
 * The shell's pane geometry: one function that turns the two persisted pairs
 * into the widths a frame is drawn with, and two that a drag is made of.
 *
 * There is exactly one source of truth per side pane — `{ collapsed, width }`,
 * the sidebar's in `settings.layout` and the explorer's per project in
 * `state/explorer.ts` — and everything on screen is derived from those. No
 * panel holds a collapse of its own, so a pane cannot be off screen with its
 * state saying open, which is the state that used to leave the person with no
 * toggle to press.
 *
 * Pixels, not shares: the sidebar is the width it was left at whatever the
 * window does, the explorer likewise, and the session absorbs the difference.
 */
import { PANE_LIMITS } from "@shared/types";

/** The two panes that have a width and a collapse. */
export type SidePane = "sidebar" | "explorer";

/** One side pane's whole state — the only thing persisted about it. */
export type PaneState = { collapsed: boolean; width: number };

/** The separator between two panes is a one-pixel line. */
export const SEPARATOR_PX = 1;

/** How far one arrow key moves a separator. */
export const KEYBOARD_STEP_PX = 16;

/**
 * What a frame is drawn with. A null width is a pane that is not rendered at
 * all — collapsed, or (for the explorer) no project — and `collapse` names
 * the panes the window is too narrow to keep, which the shell writes into
 * their state so their toggles appear.
 */
export type ResolvedPanes = {
  sidebar: number | null;
  explorer: number | null;
  collapse: readonly SidePane[];
};

function clamp(value: number, min: number, max: number): number {
  return Math.round(Math.max(min, Math.min(max, value)));
}

/** Whether the three minimums fit in `width` for a given pair of panes. */
function fits(width: number, sidebar: boolean, explorer: boolean): boolean {
  const separators = (sidebar ? SEPARATOR_PX : 0) + (explorer ? SEPARATOR_PX : 0);
  const minimums =
    (sidebar ? PANE_LIMITS.sidebar.min : 0) + (explorer ? PANE_LIMITS.explorer.min : 0);
  return width - separators - minimums >= PANE_LIMITS.session.min;
}

/**
 * The widths for one frame.
 *
 * Order matters twice. When the window cannot hold all three minimums the
 * explorer gives way first and the sidebar second — a pane is *collapsed*
 * rather than overflowed, so the person is left with a toggle rather than
 * with a session pane pushed off the right of the window. And when the
 * minimums fit but the stored widths do not, the explorer is shrunk first
 * and the sidebar only after the explorer is at its floor.
 */
export function resolvePanes({
  width,
  sidebar,
  explorer,
}: {
  /** The shell row's width in pixels. */
  width: number;
  sidebar: PaneState;
  /** Null when there is no project: no explorer pane exists to size. */
  explorer: PaneState | null;
}): ResolvedPanes {
  const collapse: SidePane[] = [];
  let sidebarOn = !sidebar.collapsed;
  let explorerOn = explorer !== null && !explorer.collapsed;
  // A width of zero is the first frame, before anything has been measured.
  if (width > 0) {
    if (explorerOn && !fits(width, sidebarOn, true)) {
      explorerOn = false;
      collapse.push("explorer");
    }
    if (sidebarOn && !fits(width, true, explorerOn)) {
      sidebarOn = false;
      collapse.push("sidebar");
    }
  }

  const separators = (sidebarOn ? SEPARATOR_PX : 0) + (explorerOn ? SEPARATOR_PX : 0);
  // What the two side panes may divide between them: the row, less the
  // separators, less the floor the session keeps whatever they do.
  const budget = width - separators - PANE_LIMITS.session.min;

  let sidebarWidth = sidebarOn
    ? clamp(sidebar.width, PANE_LIMITS.sidebar.min, PANE_LIMITS.sidebar.max)
    : null;
  let explorerWidth: number | null = null;
  if (explorerOn && explorer) {
    const room = budget - (sidebarWidth ?? 0);
    explorerWidth = clamp(explorer.width, PANE_LIMITS.explorer.min, Math.max(room, PANE_LIMITS.explorer.min));
    // The explorer is at its floor and still does not fit: the sidebar gives
    // up the rest of the difference, down to its own minimum. It cannot go
    // under it — `fits` above guaranteed the minimums fit.
    if (sidebarWidth !== null && explorerWidth > room) {
      sidebarWidth = clamp(budget - explorerWidth, PANE_LIMITS.sidebar.min, PANE_LIMITS.sidebar.max);
    }
  }

  return { sidebar: sidebarWidth, explorer: explorerWidth, collapse };
}

/** The widest a pane may be drawn, given the window and its neighbour. */
export function maxWidthOf(
  pane: SidePane,
  { width, other }: { width: number; other: number | null },
): number {
  if (pane === "sidebar") {
    return Math.min(
      PANE_LIMITS.sidebar.max,
      Math.max(
        PANE_LIMITS.sidebar.min,
        width - PANE_LIMITS.session.min - (other ?? 0) - SEPARATOR_PX * (other === null ? 1 : 2),
      ),
    );
  }
  return Math.max(
    PANE_LIMITS.explorer.min,
    width - PANE_LIMITS.session.min - (other ?? 0) - SEPARATOR_PX * (other === null ? 1 : 2),
  );
}

/**
 * Where a drag leaves a pane.
 *
 * `collapsed` is the overshoot rule: a drag that goes 40px past the pane's
 * minimum means "close it", and the width returned is the last good one, so
 * the toggle brings the pane back at the size it had rather than at its floor.
 * Anything short of that is clamped and the pane stays open — a drag that
 * stops at the minimum has not asked for anything else.
 */
export function dragOutcome({
  pane,
  requested,
  remembered,
  max,
}: {
  pane: SidePane;
  /** The width the pointer is asking for, unclamped. */
  requested: number;
  /** The pane's width before the drag started. */
  remembered: number;
  max: number;
}): { width: number; collapsed: boolean } {
  const min = pane === "sidebar" ? PANE_LIMITS.sidebar.min : PANE_LIMITS.explorer.min;
  if (requested < min - PANE_LIMITS.overshoot) {
    return { width: remembered, collapsed: true };
  }
  return { width: clamp(requested, min, Math.max(min, max)), collapsed: false };
}
